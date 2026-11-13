import SwiftUI
import UIKit
import WebKit

/// Thin WKWebView shell pointed at the in-process server on 127.0.0.1.
struct LocalWebView: UIViewRepresentable {
    let url: URL
    /// Reported when the page cannot load or renders empty, so a white screen
    /// still explains itself.
    var onIssue: (String) -> Void = { _ in }
    /// The desktop backend opens Edge for the official login; on iOS the app
    /// shows a native WKWebView instead and imports the cookies afterwards.
    var onLoginRequest: (String, String?) -> Void = { _, _ in }
    /// Result text for an .ics import (the timetable export ends up here).
    var onCalendarImport: (String) -> Void = { _ in }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.userContentController.add(context.coordinator, name: "login")
        let bridge = WKUserScript(source: """
            (function () {
                const native = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.login;
                if (!native) { return; }
                const original = window.fetch;
                window.fetch = function (input, init) {
                    try {
                        const url = typeof input === 'string' ? input : (input && input.url) || '';
                        const match = url.match(/\\/api\\/v1\\/auth\\/([a-z]+)\\/browser(?:\\?|$)/);
                        if (match) {
                            let target = null;
                            try { target = init && init.body ? JSON.parse(init.body).target : null; } catch (e) {}
                            native.postMessage({ provider: match[1], target: target });
                            return Promise.resolve(new Response('{"launching":true}', {
                                status: 200, headers: { 'Content-Type': 'application/json' }
                            }));
                        }
                    } catch (e) {}
                    return original.apply(this, arguments);
                };
            })();
            """, injectionTime: .atDocumentStart, forMainFrameOnly: true)
        configuration.userContentController.addUserScript(bridge)
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

    func makeCoordinator() -> Coordinator {
        Coordinator(base: url, onIssue: onIssue, onLoginRequest: onLoginRequest,
                    onCalendarImport: onCalendarImport)
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler, WKDownloadDelegate {
        private let base: URL
        private let onIssue: (String) -> Void
        private let onLoginRequest: (String, String?) -> Void
        private let onCalendarImport: (String) -> Void
        private var destinations: [ObjectIdentifier: URL] = [:]

        init(base: URL, onIssue: @escaping (String) -> Void,
             onLoginRequest: @escaping (String, String?) -> Void,
             onCalendarImport: @escaping (String) -> Void) {
            self.base = base
            self.onIssue = onIssue
            self.onLoginRequest = onLoginRequest
            self.onCalendarImport = onCalendarImport
        }

        // MARK: - Downloads (.ics timetable export)

        func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
            download.delegate = self
        }

        func download(_ download: WKDownload,
                      decideDestinationUsing response: URLResponse,
                      suggestedFilename: String,
                      completionHandler: @escaping (URL?) -> Void) {
            let directory = FileManager.default.temporaryDirectory
            let target = directory.appendingPathComponent(suggestedFilename.isEmpty ? "campusMate.ics" : suggestedFilename)
            try? FileManager.default.removeItem(at: target)
            destinations[ObjectIdentifier(download)] = target
            completionHandler(target)
        }

        func downloadDidFinish(_ download: WKDownload) {
            guard let url = destinations.removeValue(forKey: ObjectIdentifier(download)),
                  url.pathExtension.lowercased() == "ics" else { return }
            ICSImporter.importFile(at: url) { result in
                DispatchQueue.main.async {
                    switch result {
                    case .success(let count):
                        self.onCalendarImport(count == 0 ? "日程已在日历中，无需重复导入。" : "已导入 \(count) 个日程到日历。")
                    case .failure(let error):
                        self.onCalendarImport(error.localizedDescription)
                    }
                }
            }
        }

        func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
            onCalendarImport("导出失败: \(error.localizedDescription)")
        }

        func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == "login",
                  let body = message.body as? [String: Any],
                  let provider = body["provider"] as? String else { return }
            onLoginRequest(provider, body["target"] as? String)
        }

        /// Keep the app inside its own origin; anything else opens in Safari.
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let target = navigationAction.request.url else {
                decisionHandler(.allow)
                return
            }
            if navigationAction.shouldPerformDownload {
                decisionHandler(.download)
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
