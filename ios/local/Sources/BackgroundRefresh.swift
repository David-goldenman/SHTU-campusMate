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

    private static let notifiedKey = "campusMate.notified.notices"
    private static let lastPassKey = "campusMate.background.lastPass"
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
        _ = try? await pass()
    }

    // MARK: - One sync pass

    private static func pass() async throws {
        guard case .ready(let port) = LocalRuntime.shared.state else {
            throw Failure("本地服务尚未就绪")
        }
        let base = URL(string: "http://127.0.0.1:\(port)")!
        let token = try await bootstrapToken(base)
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
        UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: lastPassKey)
        await deliver(items)
    }

    private static func deliver(_ items: [[String: Any]]) async {
        var notified = Set(UserDefaults.standard.stringArray(forKey: notifiedKey) ?? [])
        let center = UNUserNotificationCenter.current()
        for item in items {
            guard let identity = item["id"] as? String,
                  item["read"] as? Bool != true,
                  item["expired"] as? Bool != true,
                  item["active"] as? Bool != false,
                  !notified.contains(identity) else { continue }
            let content = UNMutableNotificationContent()
            content.title = item["title"] as? String ?? "campusMate"
            content.body = item["summary"] as? String ?? ""
            if item["importance"] as? String == "urgent" { content.sound = .default }
            let request = UNNotificationRequest(identifier: identity, content: content, trigger: nil)
            try? await center.add(request)
            notified.insert(identity)
        }
        // Keep the set from growing forever; notice ids are stable per revision.
        let trimmed = Array(notified.suffix(400))
        UserDefaults.standard.set(trimmed, forKey: notifiedKey)
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
