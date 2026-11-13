import SwiftUI
import WebKit

/// Native login window for iOS: loads the official page in a WKWebView, then
/// hands the resulting cookies back to the local backend, which validates them
/// and imports the session (the desktop build does the same through Edge).
struct LoginSheet: View {
    let provider: String
    let target: String?
    let port: Int
    let onFinished: () -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var url: URL?
    @State private var message = "正在打开登录页…"
    @State private var busy = false

    private var base: String { "http://127.0.0.1:\(port)" }

    var body: some View {
        NavigationStack {
            Group {
                if let url {
                    LoginWebView(url: url)
                } else {
                    ProgressView(message).frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .navigationTitle("登录 \(provider)")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(busy ? "连接中…" : "登录完成") { finish() }
                        .disabled(busy || url == nil)
                }
            }
            .safeAreaInset(edge: .bottom) {
                Text(message)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(8)
            }
        }
        .task { await loadLoginURL() }
    }

    private func loadLoginURL() async {
        var components = URLComponents(string: base + "/api/v1/auth/\(provider)/login-url")
        if let target { components?.queryItems = [URLQueryItem(name: "target", value: target)] }
        guard let endpoint = components?.url else { return }
        do {
            let (data, _) = try await URLSession.shared.data(from: endpoint)
            struct Payload: Decodable { let url: String }
            let payload = try JSONDecoder().decode(Payload.self, from: data)
            url = URL(string: payload.url)
            message = "在窗口里完成登录后点“登录完成”。"
        } catch {
            message = "无法获取登录地址: \(error.localizedDescription)"
        }
    }

    private func finish() {
        busy = true
        message = "正在导入登录状态…"
        WKWebsiteDataStore.default().httpCookieStore.getAllCookies { cookies in
            let payload = cookies.map { cookie -> [String: Any] in
                [
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                    "secure": cookie.isSecure,
                    "httpOnly": cookie.isHTTPOnly,
                    "expires": cookie.expiresDate.map { Int($0.timeIntervalSince1970) } ?? NSNull(),
                ]
            }
            Task { await post(cookies: payload) }
        }
    }

    private func post(cookies: [[String: Any]]) async {
        do {
            // The backend protects writes with the token handed out by bootstrap.
            let (bootstrap, _) = try await URLSession.shared.data(from: URL(string: base + "/api/v1/bootstrap")!)
            struct Boot: Decodable { let csrf_token: String }
            let token = try JSONDecoder().decode(Boot.self, from: bootstrap).csrf_token

            var request = URLRequest(url: URL(string: base + "/api/v1/auth/\(provider)/cookies")!)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue(token, forHTTPHeaderField: "X-Framework-Token")
            request.httpBody = try JSONSerialization.data(withJSONObject: [
                "cookies": cookies,
                "user_agent": "campusMate-iOS",
            ])
            let (data, response) = try await URLSession.shared.data(for: request)
            let status = (response as? HTTPURLResponse)?.statusCode ?? -1
            if status == 200 {
                await MainActor.run {
                    message = "登录已连接。"
                    onFinished()
                    dismiss()
                }
            } else {
                let text = String(data: data, encoding: .utf8) ?? ""
                await MainActor.run {
                    busy = false
                    message = "导入失败（HTTP \(status)）: \(text.prefix(200))"
                }
            }
        } catch {
            await MainActor.run {
                busy = false
                message = "导入失败: \(error.localizedDescription)"
            }
        }
    }
}

/// Plain WKWebView wrapper used inside the sheet.
struct LoginWebView: UIViewRepresentable {
    let url: URL

    func makeUIView(context: Context) -> WKWebView {
        let view = WKWebView(frame: .zero, configuration: WKWebViewConfiguration())
        view.load(URLRequest(url: url))
        return view
    }

    func updateUIView(_ view: WKWebView, context: Context) {}
}
