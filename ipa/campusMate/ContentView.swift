import SwiftUI

struct ContentView: View {
    @State private var settings = ServerSettings.load()
    @State private var editing = false
    @State private var reloadToken = 0
    @State private var reachable = true

    var body: some View {
        if let settings {
            workspace(settings)
        } else {
            SetupView(initial: nil, title: "连接 campusMate") { value in
                value.save()
                self.settings = value
                reachable = true
            }
        }
    }

    private func workspace(_ settings: ServerSettings) -> some View {
        ZStack {
            CampusWebView(settings: settings, reloadToken: reloadToken, reachable: $reachable)
                .ignoresSafeArea(edges: .bottom)
            if !reachable {
                OfflineNotice { reloadToken += 1 }
            }
        }
        .safeAreaInset(edge: .top, spacing: 0) {
            HStack(spacing: 18) {
                Text(settings.displayAddress)
                    .font(.footnote.monospaced())
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                Spacer(minLength: 0)
                Button {
                    reloadToken += 1
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .accessibilityLabel("刷新")
                Button {
                    editing = true
                } label: {
                    Image(systemName: "gearshape")
                }
                .accessibilityLabel("服务器地址")
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(.bar)
        }
        .sheet(isPresented: $editing) {
            SetupView(initial: settings, title: "服务器地址") { value in
                value.save()
                self.settings = value
                reachable = true
                reloadToken += 1
                editing = false
            } onCancel: {
                editing = false
            }
        }
    }
}

private struct OfflineNotice: View {
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "wifi.slash")
                .font(.largeTitle)
                .foregroundStyle(.secondary)
            Text("无法连接电脑上的 campusMate")
                .font(.headline)
            Text("确认电脑仍在运行、手机与电脑连接同一个 Wi-Fi，再核对地址与配对码。")
                .font(.footnote)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
            Button("重试", action: retry)
                .buttonStyle(.borderedProminent)
        }
        .padding(24)
        .frame(maxWidth: 380)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
        .padding(24)
    }
}
