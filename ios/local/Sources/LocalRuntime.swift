import Foundation
import WebKit

/// Boots the embedded CPython once and reports the port its local server bound.
/// The Python side writes the port to a file, so nothing has to be guessed or
/// shared through fragile in-memory callbacks.
final class LocalRuntime: ObservableObject {
    /// One runtime per process; background refresh reads its port.
    static let shared = LocalRuntime()

    enum State {
        case idle
        case starting
        case ready(Int)
        case failed(String)
    }

    @Published private(set) var state: State = .idle
    /// One-line progress text shown at the bottom of every screen; it also ends
    /// up in Documents/data/launch.log so a blank screen still tells a story.
    @Published private(set) var info = "准备启动"
    @Published private(set) var showInfo = true

    private var started = false
    private var logPath = ""
    private var launchLogPath = ""

    func start() {
        guard !started else { return }
        started = true
        state = .starting

        let bundle = Bundle.main.bundleURL
        let home = bundle.appendingPathComponent("python").path
        let script = bundle.appendingPathComponent("boot.py").path
        let portFile = FileManager.default.temporaryDirectory
            .appendingPathComponent("campusmate-local-port.txt")

        // The bundle is read-only at runtime; keep settings, SQLite and the
        // module data directory in the app's Documents folder.
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let dataDirectory = documents.appendingPathComponent("data")
        do {
            try FileManager.default.createDirectory(at: dataDirectory, withIntermediateDirectories: true)
            note("数据目录: \(dataDirectory.path)")
        } catch {
            note("无法创建数据目录: \(error.localizedDescription)")
        }
        setenv("CAMPUS_DATA_DIR", dataDirectory.path, 1)
        #if DEBUG
        // Development builds expose the sidebar's developer panel; release
        // builds never set this flag (ios/DEVELOPMENT.md).
        setenv("CAMPUS_DEV_BUILD", "1", 1)
        #else
        unsetenv("CAMPUS_DEV_BUILD")
        #endif
        logPath = dataDirectory.appendingPathComponent("python.log").path
        launchLogPath = dataDirectory.appendingPathComponent("launch.log").path
        // Overwrite installs keep WKWebView's disk cache; when the binary is
        // newer than the last run, drop the cached page and scripts.
        Self.purgeWebCacheIfRebuilt()
        try? FileManager.default.removeItem(at: portFile)

        note("启动 Python: home=\(home)")

        DispatchQueue.global(qos: .userInitiated).async {
            // Redirect the process-level streams before the interpreter starts:
            // this catches Python tracebacks and any C-level output.
            _ = freopen(self.logPath, "a", stderr)
            _ = freopen(self.logPath, "a", stdout)
            let executable = Bundle.main.executableURL?.path
                ?? bundle.appendingPathComponent("campusMateLocal").path
            let code = cm_start_python(home, script, portFile.path, executable, self.logPath)
            DispatchQueue.main.async {
                if code != 0 {
                    let tail = Self.tail(of: self.logPath, lines: 12)
                    self.state = .failed("Python 解释器启动失败（错误码 \(code)）。\n\n\(tail)")
                } else {
                    self.note("Python 退出（服务已停止）")
                }
            }
        }

        waitForPort(portFile, attempts: 0)
    }

    // MARK: - Caches

    private static func purgeWebCacheIfRebuilt() {
        let defaults = UserDefaults.standard
        let key = "campusMate.buildStamp"
        let stamp = buildStamp()
        guard defaults.string(forKey: key) != stamp else { return }
        defaults.set(stamp, forKey: key)
        WKWebsiteDataStore.default().removeData(
            ofTypes: WKWebsiteDataStore.allWebsiteDataTypes(),
            modifiedSince: .distantPast) {}
    }

    private static func buildStamp() -> String {
        guard let executable = Bundle.main.executableURL,
              let attributes = try? FileManager.default.attributesOfItem(atPath: executable.path),
              let modified = attributes[.modificationDate] as? Date else { return "unknown" }
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? ""
        return "\(version)/\(Int(modified.timeIntervalSince1970))"
    }

    // MARK: - Diagnostics

    private func note(_ message: String) {
        info = message
        guard !launchLogPath.isEmpty else { return }
        let line = "[\(Self.stamp())] \(message)\n"
        if let handle = FileHandle(forWritingAtPath: launchLogPath) {
            handle.seekToEndOfFile()
            handle.write(Data(line.utf8))
            handle.closeFile()
        } else {
            try? line.write(toFile: launchLogPath, atomically: true, encoding: .utf8)
        }
    }

    private static func stamp() -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss"
        return formatter.string(from: Date())
    }

    /// Last lines of the Python log, shown in the failure screen so the error
    /// is visible without Xcode or the Files app.
    static func tail(of path: String, lines: Int) -> String {
        guard let text = try? String(contentsOfFile: path, encoding: .utf8) else {
            return "（无法读取 \(path)）"
        }
        return text.split(separator: "\n", omittingEmptySubsequences: false).suffix(lines).joined(separator: "\n")
    }

    // MARK: - Readiness

    private func waitForPort(_ url: URL, attempts: Int) {
        guard attempts < 200 else {
            note("等待端口超时")
            state = .failed("本地服务未能在 20 秒内就绪。\n\n\(Self.tail(of: logPath, lines: 12))")
            return
        }
        if let text = try? String(contentsOf: url, encoding: .utf8),
           let port = Int(text.trimmingCharacters(in: .whitespacesAndNewlines)) {
            note("端口 \(port)，检查服务")
            checkHealth(port: port, attempts: 0)
            return
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { [weak self] in
            self?.waitForPort(url, attempts: attempts + 1)
        }
    }

    private func checkHealth(port: Int, attempts: Int) {
        guard attempts < 40 else {
            note("健康检查失败")
            state = .failed("本地服务已监听 \(port) 但请求 /api/v1/health 失败。\n\n\(Self.tail(of: logPath, lines: 12))")
            return
        }
        guard let url = URL(string: "http://127.0.0.1:\(port)/api/v1/health") else { return }
        var request = URLRequest(url: url)
        request.timeoutInterval = 2
        URLSession.shared.dataTask(with: request) { [weak self] _, response, error in
            DispatchQueue.main.async {
                guard let self else { return }
                if let http = response as? HTTPURLResponse, http.statusCode == 200 {
                    self.note("服务就绪 :\(port)")
                    self.state = .ready(port)
                    DispatchQueue.main.asyncAfter(deadline: .now() + 4) {
                        self.showInfo = false
                    }
                } else {
                    let reason = error?.localizedDescription ?? "HTTP \((response as? HTTPURLResponse)?.statusCode ?? -1)"
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                        self.checkHealth(port: port, attempts: attempts + 1)
                    }
                    self.note("等待服务（\(reason)）")
                }
            }
        }.resume()
    }
}
