import SwiftUI
import UIKit
import WebKit

/// Shows the desktop workspace as-is and keeps every navigation inside the
/// paired computer. Exports (.ics), popups and JavaScript dialogs are forwarded
/// to the system so the phone behaves like a browser tab.
struct CampusWebView: UIViewRepresentable {
    let settings: ServerSettings
    let reloadToken: Int
    @Binding var reachable: Bool

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        configuration.allowsInlineMediaPlayback = true
        configuration.applicationNameForUserAgent = "campusMate"
        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true
        webView.isOpaque = false
        webView.backgroundColor = UIColor(red: 0.302, green: 0.455, blue: 0.988, alpha: 1)
        webView.scrollView.backgroundColor = webView.backgroundColor
        context.coordinator.open(webView, settings: settings, token: reloadToken)
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        context.coordinator.parent = self
        context.coordinator.open(webView, settings: settings, token: reloadToken)
    }

    static func dismantleUIView(_ webView: WKWebView, coordinator: Coordinator) {
        webView.stopLoading()
        webView.navigationDelegate = nil
        webView.uiDelegate = nil
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
        var parent: CampusWebView
        private var opened = ""
        private var pending: URL?

        init(_ parent: CampusWebView) { self.parent = parent }

        func open(_ webView: WKWebView, settings: ServerSettings, token: Int) {
            let target = "\(settings.displayAddress)#\(token)"
            guard target != opened else { return }
            opened = target
            DispatchQueue.main.async { [weak self] in self?.parent.reachable = true }
            guard let url = settings.pairingURL else { return }
            webView.load(URLRequest(url: url, cachePolicy: .reloadRevalidatingCacheData, timeoutInterval: 30))
        }

        // MARK: - Navigation

        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = navigationAction.request.url else { return decisionHandler(.cancel) }
            if ["about", "data", "blob", "file"].contains(url.scheme ?? "") { return decisionHandler(.allow) }
            guard let origin = parent.settings.baseURL, url.host == origin.host, url.port == origin.port else {
                UIApplication.shared.open(url)
                return decisionHandler(.cancel)
            }
            decisionHandler(.allow)
        }

        func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
            let response = navigationResponse.response
            let disposition = (response as? HTTPURLResponse)?.value(forHTTPHeaderField: "Content-Disposition")?.lowercased() ?? ""
            if !navigationResponse.canShowMIMEType || disposition.contains("attachment") || response.url?.pathExtension.lowercased() == "ics" {
                return decisionHandler(.download)
            }
            decisionHandler(.allow)
        }

        func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
            download.delegate = self
        }

        func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
            download.delegate = self
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            parent.reachable = true
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            guard (error as NSError).code != NSURLErrorCancelled else { return }
            parent.reachable = false
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            guard (error as NSError).code != NSURLErrorCancelled else { return }
            parent.reachable = false
        }

        func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
            if let url = parent.settings.pairingURL { webView.load(URLRequest(url: url)) }
        }


        // MARK: - Export files

        func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
            let directory = FileManager.default.temporaryDirectory.appendingPathComponent("campusMate", isDirectory: true)
            try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let destination = directory.appendingPathComponent(suggestedFilename.isEmpty ? "campusMate-export" : suggestedFilename)
            try? FileManager.default.removeItem(at: destination)
            pending = destination
            completionHandler(destination)
        }

        func downloadDidFinish(_ download: WKDownload) {
            guard let file = pending else { return }
            pending = nil
            share(file)
        }

        func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
            pending = nil
        }

        // MARK: - Windows and dialogs

        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            guard let url = navigationAction.request.url else { return nil }
            if url.host == parent.settings.baseURL?.host {
                webView.load(navigationAction.request)
            } else {
                UIApplication.shared.open(url)
            }
            return nil
        }

        func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
            let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: "好", style: .default) { _ in completionHandler() })
            present(alert)
        }

        func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
            let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: "取消", style: .cancel) { _ in completionHandler(false) })
            alert.addAction(UIAlertAction(title: "好", style: .default) { _ in completionHandler(true) })
            present(alert)
        }

        func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
            let alert = UIAlertController(title: nil, message: prompt, preferredStyle: .alert)
            alert.addTextField { field in
                field.text = defaultText
                field.autocapitalizationType = .none
                field.autocorrectionType = .no
            }
            alert.addAction(UIAlertAction(title: "取消", style: .cancel) { _ in completionHandler(nil) })
            alert.addAction(UIAlertAction(title: "好", style: .default) { _ in completionHandler(alert.textFields?.first?.text) })
            present(alert)
        }

        // MARK: - Presentation

        private func presenter() -> UIViewController? {
            guard let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first(where: { $0.activationState == .foregroundActive }),
                  let root = scene.windows.first(where: { $0.isKeyWindow })?.rootViewController else { return nil }
            var controller = root
            while let next = controller.presentedViewController { controller = next }
            return controller
        }

        private func present(_ alert: UIAlertController) {
            DispatchQueue.main.async {
                self.presenter()?.present(alert, animated: true)
            }
        }

        private func share(_ file: URL) {
            DispatchQueue.main.async {
                guard let presenter = self.presenter() else { return }
                let controller = UIActivityViewController(activityItems: [file], applicationActivities: nil)
                if let popover = controller.popoverPresentationController {
                    popover.sourceView = presenter.view
                    popover.sourceRect = CGRect(x: presenter.view.bounds.midX, y: presenter.view.bounds.midY, width: 0, height: 0)
                }
                presenter.present(controller, animated: true)
            }
        }
    }
}
