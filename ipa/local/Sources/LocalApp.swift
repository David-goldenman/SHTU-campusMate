import SwiftUI

@main
struct CampusMateLocalApp: App {
    @StateObject private var runtime = LocalRuntime()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(runtime)
                .task { runtime.start() }
        }
    }
}

struct RootView: View {
    @EnvironmentObject private var runtime: LocalRuntime
    @State private var pageIssue: String?

    var body: some View {
        ZStack(alignment: .bottom) {
            content
            // Always visible: on a blank page this is the only clue about how
            // far the local server got.
            Text(runtime.info)
                .font(.caption2.monospaced())
                .foregroundStyle(.secondary)
                .lineLimit(2)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(.ultraThinMaterial, in: Capsule())
                .padding(.bottom, 6)
        }
    }

    @ViewBuilder
    private var content: some View {
        switch runtime.state {
        case .ready(let port):
            LocalWebView(url: URL(string: "http://127.0.0.1:\(port)/")!) { issue in
                pageIssue = issue
            }
            .ignoresSafeArea(edges: .bottom)
            .overlay(alignment: .top) {
                if let pageIssue {
                    Text(pageIssue)
                        .font(.caption2.monospaced())
                        .foregroundStyle(.secondary)
                        .lineLimit(6)
                        .padding(8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(.ultraThinMaterial)
                }
            }
        case .failed(let message):
            StatusView(title: "本地服务启动失败", detail: message, showsProgress: false)
        case .starting:
            StatusView(title: "正在启动本地服务…", detail: "内嵌 Python 与网页资源在设备本地运行。", showsProgress: true)
        case .idle:
            StatusView(title: "准备启动…", detail: "", showsProgress: true)
        }
    }
}

private struct StatusView: View {
    let title: String
    let detail: String
    let showsProgress: Bool

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                if showsProgress {
                    ProgressView()
                } else {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.largeTitle)
                        .foregroundStyle(.secondary)
                }
                Text(title).font(.headline)
                Text(detail)
                    .font(showsProgress ? .footnote : .caption.monospaced())
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(showsProgress ? .center : .leading)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(24)
        }
    }
}
