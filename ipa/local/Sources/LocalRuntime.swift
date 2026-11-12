import Foundation

/// Boots the embedded CPython once and reports the port its local server bound.
/// The Python side writes the port to a file, so nothing has to be guessed or
/// shared through fragile in-memory callbacks.
final class LocalRuntime: ObservableObject {
    enum State {
        case idle
        case starting
        case ready(Int)
        case failed(String)
    }

    @Published private(set) var state: State = .idle
    private var started = false

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
        setenv("CAMPUS_DATA_DIR", documents.appendingPathComponent("data").path, 1)
        try? FileManager.default.removeItem(at: portFile)

        DispatchQueue.global(qos: .userInitiated).async {
            let executable = Bundle.main.executableURL?.path ?? bundle.appendingPathComponent("campusMateLocal").path
                let code = cm_start_python(home, script, portFile.path, executable)
            DispatchQueue.main.async {
                if code != 0 {
                    self.state = .failed("Python 解释器启动失败（错误码 \(code)）。")
                }
            }
        }

        waitForPort(portFile, attempts: 0)
    }

    private func waitForPort(_ url: URL, attempts: Int) {
        guard attempts < 120 else {
            state = .failed("本地服务未能在 12 秒内就绪。")
            return
        }
        if let text = try? String(contentsOf: url, encoding: .utf8),
           let port = Int(text.trimmingCharacters(in: .whitespacesAndNewlines)) {
            state = .ready(port)
            return
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { [weak self] in
            self?.waitForPort(url, attempts: attempts + 1)
        }
    }
}
