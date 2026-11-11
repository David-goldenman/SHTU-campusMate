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

    var body: some View {
        switch runtime.state {
        case .ready(let port):
            LocalWebView(url: URL(string: "http://127.0.0.1:\(port)/")!)
                .ignoresSafeArea(edges: .bottom)
        case .failed(let message):
            StatusView(title: "本地服务启动失败", detail: message, showsProgress: false)
        default:
            StatusView(title: "正在启动本地服务…", detail: "内嵌 Python 与网页资源在设备本地运行。", showsProgress: true)
        }
    }
}

private struct StatusView: View {
    let title: String
    let detail: String
    let showsProgress: Bool

    var body: some View {
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
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(28)
    }
}
