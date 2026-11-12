import SwiftUI
import UIKit
import WebKit

/// Thin WKWebView shell pointed at the in-process server on 127.0.0.1.
struct LocalWebView: UIViewRepresentable {
    let url: URL
    /// Reported when the page cannot load or renders empty, so a white screen
    /// still explains itself.
    var onIssue: (String) -> Void = { _ in }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        let script = WKUserScript(source: """
            window.__cmErrors = [];
            window.addEventListener('error', function (event) {
                window.__cmErrors.push((event.message || 'error') + ' @ ' +
                    (event.filename || '?') + ':' + (event.lineno || 0));
            });
            window.addEventListener('unhandledrejection', function (event) {
                window.__cmErrors.push('promise: ' + (event.reason && event.reason.message ? event.reason.message : event.reason));
            });
            """, injectionTime: .atDocumentStart, forMainFrameOnly: true)
        configuration.userContentController.addUserScript(script)

        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        view.allowsBackForwardNavigationGestures = false
        view.load(URLRequest(url: url))
        return view
    }

    func updateUIView(_ view: WKWebView, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(base: url, onIssue: onIssue) }

    final class Coordinator: NSObject, WKNavigationDelegate {
        private let base: URL
        private let onIssue: (String) -> Void

        init(base: URL, onIssue: @escaping (String) -> Void) {
            self.base = base
            self.onIssue = onIssue
        }

        /// Keep the app inside its own origin; anything else opens in Safari.
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let target = navigationAction.request.url else {
                decisionHandler(.allow)
                return
            }
            if target.host == base.host || target.host == nil {
                decisionHandler(.allow)
            } else {
                UIApplication.shared.open(target)
                decisionHandler(.cancel)
            }
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            onIssue("页面加载失败: \(error.localizedDescription)")
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            onIssue("页面无法连接: \(error.localizedDescription)")
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            let probe = """
                JSON.stringify({
                    title: document.title || '',
                    text: (document.body ? document.body.innerText.length : -1),
                    html: (document.body ? document.body.innerHTML.length : -1),
                    errors: (window.__cmErrors || []).slice(0, 6)
                })
                """
            webView.evaluateJavaScript(probe) { [onIssue] result, error in
                if let error {
                    onIssue("页面脚本不可用: \(error.localizedDescription)")
                    return
                }
                // Only surface something when the page is blank or broken.
                if let json = result as? String,
                   json.contains("\"text\":0") || json.contains("\"errors\":[\"") {
                    onIssue("页面空白: \(json)")
                } else if let error {
                    onIssue("页面探测失败: \(error.localizedDescription)")
                } else {
                    onIssue("")
                }
            }
        }
    }
}
