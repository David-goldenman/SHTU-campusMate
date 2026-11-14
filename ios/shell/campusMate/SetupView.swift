import SwiftUI

/// First-run and settings form: the address and pairing code printed by the
/// desktop launch window. The code unlocks the LAN address on the backend.
struct SetupView: View {
    let initial: ServerSettings?
    let title: String
    let onConnect: (ServerSettings) -> Void
    var onCancel: (() -> Void)?

    @State private var address: String
    @State private var code: String
    @State private var message = ""

    init(initial: ServerSettings?, title: String, onConnect: @escaping (ServerSettings) -> Void, onCancel: (() -> Void)? = nil) {
        self.initial = initial
        self.title = title
        self.onConnect = onConnect
        self.onCancel = onCancel
        _address = State(initialValue: initial?.displayAddress ?? "")
        _code = State(initialValue: initial?.code ?? "")
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("192.168.1.23:16666", text: $address)
                        .keyboardType(.URL)
                        .textContentType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    TextField("8 位配对码", text: $code)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                } header: {
                    Text("电脑地址")
                } footer: {
                    Text("在电脑上运行 run.cmd --share，启动窗口会显示地址与配对码。手机与电脑需要连接同一个 Wi-Fi。")
                }
                if !message.isEmpty {
                    Section {
                        Text(message)
                            .font(.footnote)
                            .foregroundStyle(.red)
                    }
                }
                Section {
                    Button("连接") { connect() }
                        .frame(maxWidth: .infinity)
                }
                Section {
                    Text("手机打开的是电脑上的同一套工作台：课表、作业、校园信息与 AI 问答都在电脑上计算。依赖电脑端登录的微信群、QQ 群消息只在电脑上使用。")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if let onCancel {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("取消", action: onCancel)
                    }
                }
            }
        }
    }

    private func connect() {
        guard let value = ServerSettings.parse(address: address, code: code) else {
            message = "地址格式不正确。示例：192.168.1.23:16666，配对码为 8 位小写字母或数字。"
            return
        }
        if value.code.isEmpty && !["127.0.0.1", "localhost"].contains(value.host) {
            message = "请填写电脑窗口显示的 8 位配对码。"
            return
        }
        onConnect(value)
    }
}
