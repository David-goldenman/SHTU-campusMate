import BackgroundTasks
import Foundation
import UIKit
import UserNotifications

/// Keeps the local server doing work while the app is in the background and
/// mirrors new campusMate notices to the system notification centre.
///
/// iOS gives a background-refresh task roughly 30 seconds, so a pass only asks
/// the local API to sync its sources and reads back the notice list; the
/// modules keep their own caches, and anything missed runs again next time.
enum BackgroundRefresh {
    static var taskIdentifier: String {
        (Bundle.main.bundleIdentifier ?? "edu.shanghaitech.campusmate.local.dev") + ".refresh"
    }

    /// A longer, system-scheduled window (minutes instead of ~30 s), used when
    /// iOS decides the device is idle enough — typically while charging.
    static var processingIdentifier: String {
        (Bundle.main.bundleIdentifier ?? "edu.shanghaitech.campusmate.local.dev") + ".sync"
    }

    private static let notifiedKey = "campusMate.notified.notices"
    private static let hashesKey = "campusMate.notified.hashes"
    private static let lastPassKey = "campusMate.background.lastPass"
    /// A wake-up within this window is skipped: iOS may call the refresh task
    /// and the background keep-alive back to back.
    private static let passCooldown: TimeInterval = 5 * 60
    /// Never flood the lock screen; the rest arrives on the next pass.
    private static let batchLimit = 3
    private static var backgroundTask: UIBackgroundTaskIdentifier = .invalid

    // MARK: - Registration

    static func register() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: taskIdentifier, using: nil) { task in
            guard let task = task as? BGAppRefreshTask else {
                task.setTaskCompleted(success: false)
                return
            }
            handle(task)
        }
        BGTaskScheduler.shared.register(forTaskWithIdentifier: processingIdentifier, using: nil) { task in
            guard let task = task as? BGProcessingTask else {
                task.setTaskCompleted(success: false)
                return
            }
            handleProcessing(task)
        }
        UNUserNotificationCenter.current().delegate = NotificationDelegate.shared
    }

    static func requestAuthorization() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { _, _ in }
    }

    static func schedule(after seconds: TimeInterval = 15 * 60) {
        let request = BGAppRefreshTaskRequest(identifier: taskIdentifier)
        request.earliestBeginDate = Date(timeIntervalSinceNow: seconds)
        try? BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: taskIdentifier)
        try? BGTaskScheduler.shared.submit(request)
        // Processing tasks are allowed to run much longer but may wait hours
        // for a convenient moment; ask for one roughly every four hours.
        let processing = BGProcessingTaskRequest(identifier: processingIdentifier)
        processing.requiresNetworkConnectivity = true
        processing.requiresExternalPower = false
        processing.earliestBeginDate = Date(timeIntervalSinceNow: 4 * 60 * 60)
        try? BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: processingIdentifier)
        try? BGTaskScheduler.shared.submit(processing)
    }

    /// Runs a short pass immediately; used when the app goes to the background
    /// so mail that arrived while the screen was open is classified right away.
    static func keepAlive() {
        endBackgroundTask()
        backgroundTask = UIApplication.shared.beginBackgroundTask(withName: "campusMate.sync") {
            endBackgroundTask()
        }
        Task {
            _ = try? await pass()
            endBackgroundTask()
        }
    }

    private static func endBackgroundTask() {
        guard backgroundTask != .invalid else { return }
        UIApplication.shared.endBackgroundTask(backgroundTask)
        backgroundTask = .invalid
    }

    // MARK: - Background task

    private static func handle(_ task: BGAppRefreshTask) {
        schedule()
        let work = Task { () -> Bool in
            do {
                try await pass()
                return true
            } catch {
                return false
            }
        }
        task.expirationHandler = { work.cancel() }
        Task { task.setTaskCompleted(success: await work.value) }
    }

    /// Manual trigger from the developer panel: proves notification delivery.
    static func sendTestNotification() {
        let content = UNMutableNotificationContent()
        content.title = "campusMate 测试通知"
        content.body = "开发者模式：通知链路正常，后台任务会继续同步邮件与作业。"
        content.sound = .default
        let request = UNNotificationRequest(identifier: "campusMate.dev.test.\(UUID().uuidString)",
                                            content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }

    /// Manual trigger from the developer panel.
    static func runNow() async {
        _ = try? await pass(force: true)
    }

    private static func handleProcessing(_ task: BGProcessingTask) {
        schedule()
        let work = Task { () -> Bool in
            do {
                try await pass(force: true)
                return true
            } catch {
                return false
            }
        }
        task.expirationHandler = { work.cancel() }
        Task { task.setTaskCompleted(success: await work.value) }
    }

    // MARK: - One sync pass

    private static func pass(force: Bool = false) async throws {
        guard case .ready(let port) = LocalRuntime.shared.state else {
            throw Failure("本地服务尚未就绪")
        }
        let defaults = UserDefaults.standard
        let base = URL(string: "http://127.0.0.1:\(port)")!
        let recent = (defaults.object(forKey: lastPassKey) as? Double).map { Date().timeIntervalSince1970 - $0 < passCooldown } ?? false
        let token = try await bootstrapToken(base)
        guard force || !recent else {
            // Nothing new to fetch, but keep the deterministic reminders fresh.
            await scheduleDeadlines(base: base, token: token)
            return
        }
        defaults.set(Date().timeIntervalSince1970, forKey: lastPassKey)
        // Each call is optional: a disabled module answers 404/409 and that
        // must not stop the rest of the pass.
        for path in ["/api/v1/modules/mail/sync",
                     "/api/v1/modules/assignments/sync",
                     "/api/v1/modules/timetable/schedule/sync",
                     "/api/v1/modules/notifications/generate"] {
            _ = try? await call(base, path, token: token, method: "POST")
        }
        guard let data = try? await call(base, "/api/v1/modules/notifications/snapshot", token: token),
              let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let items = payload["items"] as? [[String: Any]] else { return }
        await deliver(items)
        await scheduleDeadlines(base: base, token: token)
    }

    /// Deadline reminders are scheduled with calendar triggers, so iOS fires
    /// them even when campusMate has not been opened for days. Re-running is
    /// idempotent: the identifier carries the item and the offset.
    private static func scheduleDeadlines(base: URL, token: String) async {
        guard let data = try? await call(base, "/api/v1/modules/assignments/snapshot", token: token),
              let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let pending = payload["pending"] as? [[String: Any]] else { return }
        let center = UNUserNotificationCenter.current()
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let fallback = ISO8601DateFormatter()
        var scheduled = 0
        for item in pending.prefix(20) {
            guard let identity = item["id"] as? String,
                  let title = item["title"] as? String,
                  let text = item["due_at"] as? String,
                  let due = parser.date(from: text) ?? fallback.date(from: text) else { continue }
            let course = item["course_title"] as? String ?? ""
            for (offset, label) in [(86_400.0, "还有 1 天"), (10_800.0, "还有 3 小时")] {
                let fire = due.addingTimeInterval(-offset)
                guard fire > Date().addingTimeInterval(60) else { continue }
                let content = UNMutableNotificationContent()
                content.title = "作业截止" + label
                content.body = [course, title].filter { !$0.isEmpty }.joined(separator: " · ")
                content.sound = .default
                let parts = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: fire)
                let request = UNNotificationRequest(identifier: "deadline:\(identity):\(Int(offset))",
                                                    content: content,
                                                    trigger: UNCalendarNotificationTrigger(dateMatching: parts, repeats: false))
                try? await center.add(request)
                scheduled += 1
            }
        }
        if scheduled > 0 {
            UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: "campusMate.deadlines.scheduled")
        }
    }

    /// Called when the app becomes ready: refresh the reminders without a sync.
    static func scheduleDeadlinesNow() async {
        guard case .ready(let port) = LocalRuntime.shared.state else { return }
        let base = URL(string: "http://127.0.0.1:\(port)")!
        guard let token = try? await bootstrapToken(base) else { return }
        await scheduleDeadlines(base: base, token: token)
    }

    private static func deliver(_ items: [[String: Any]]) async {
        let defaults = UserDefaults.standard
        var notified = Set(defaults.stringArray(forKey: notifiedKey) ?? [])
        var hashes = Set(defaults.stringArray(forKey: hashesKey) ?? [])
        let center = UNUserNotificationCenter.current()
        // Notices that are still on the lock screen must not be posted again
        // after a relaunch: the system keeps them across app starts.
        let onScreen = Set(await center.deliveredNotifications().map(\.request.identifier))
        var sent = 0
        for item in items {
            guard sent < batchLimit else { break }
            guard let identity = item["id"] as? String,
                  item["read"] as? Bool != true,
                  item["expired"] as? Bool != true,
                  item["active"] as? Bool != false,
                  !notified.contains(identity),
                  !onScreen.contains(identity) else { continue }
            let title = item["title"] as? String ?? "campusMate"
            let body = item["summary"] as? String ?? ""
            // The notice id can change when the module regenerates its list;
            // identical content must still only alert once.
            let digest = contentHash(title + "\u{1F}" + body)
            guard !hashes.contains(digest) else { continue }
            let content = UNMutableNotificationContent()
            content.title = title
            content.body = body
            if item["importance"] as? String == "urgent" { content.sound = .default }
            try? await center.add(UNNotificationRequest(identifier: identity, content: content, trigger: nil))
            notified.insert(identity)
            hashes.insert(digest)
            sent += 1
            // Persist per notification: a crash must not replay the batch.
            defaults.set(Array(notified.suffix(400)), forKey: notifiedKey)
            defaults.set(Array(hashes.suffix(400)), forKey: hashesKey)
        }
    }

    private static func contentHash(_ text: String) -> String {
        var hash: UInt64 = 0xcbf29ce484222325
        for byte in text.utf8 {
            hash ^= UInt64(byte)
            hash = hash &* 0x100000001b3
        }
        return String(hash, radix: 16)
    }

    // MARK: - Local API

    private static func bootstrapToken(_ base: URL) async throws -> String {
        let (data, _) = try await URLSession.shared.data(from: base.appendingPathComponent("api/v1/bootstrap"))
        guard let payload = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let token = payload["csrf_token"] as? String else {
            throw Failure("无法读取本地服务令牌")
        }
        return token
    }

    @discardableResult
    private static func call(_ base: URL, _ path: String, token: String, method: String = "GET") async throws -> Data {
        var request = URLRequest(url: base.appendingPathComponent(String(path.dropFirst())))
        request.httpMethod = method
        request.setValue(token, forHTTPHeaderField: "X-Framework-Token")
        request.timeoutInterval = 25
        let (data, response) = try await URLSession.shared.data(for: request)
        if let http = response as? HTTPURLResponse, http.statusCode >= 500 {
            throw Failure("本地服务返回 \(http.statusCode)")
        }
        return data
    }

    struct Failure: LocalizedError {
        let message: String
        init(_ message: String) { self.message = message }
        var errorDescription: String? { message }
    }
}

/// Registers the background task before the application finishes launching;
/// BGTaskScheduler rejects registrations that happen later.
final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        BackgroundRefresh.register()
        return true
    }
}

/// Shows banners while the app is open as well.
final class NotificationDelegate: NSObject, UNUserNotificationCenterDelegate {
    static let shared = NotificationDelegate()

    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }
}
