import Foundation

/// Where the desktop workspace lives, plus the pairing code that proves the
/// phone was allowed to connect. The launch window prints both values and they
/// are kept in UserDefaults so a restart reconnects without retyping.
struct ServerSettings: Codable, Equatable {
    static let defaultPort = 16666
    static let storageKey = "campusMate.server"

    var host: String
    var port: Int
    var code: String

    var displayAddress: String { "\(host):\(port)" }

    /// Origin without the pairing code; navigation is kept inside it.
    var baseURL: URL? { URL(string: "http://\(host):\(port)") }

    /// The first request carries the code, then the backend sets a cookie and
    /// redirects, so later requests and reloads stay free of the code.
    var pairingURL: URL? {
        guard var components = URLComponents(string: "http://\(host):\(port)/") else { return nil }
        if !code.isEmpty {
            components.queryItems = [URLQueryItem(name: "pair", value: code)]
        }
        return components.url
    }

    static func parse(address: String, code: String) -> ServerSettings? {
        var host = address.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        for scheme in ["http://", "https://"] where host.hasPrefix(scheme) {
            host.removeFirst(scheme.count)
        }
        while host.hasSuffix("/") { host.removeLast() }
        guard !host.isEmpty, host.count <= 260 else { return nil }
        guard host.rangeOfCharacter(from: CharacterSet(charactersIn: "/?#@ \t")) == nil else { return nil }

        var port = defaultPort
        if let colon = host.lastIndex(of: ":") {
            let value = String(host[host.index(after: colon)...])
            guard let number = Int(value), (1...65535).contains(number) else { return nil }
            port = number
            host = String(host[..<colon])
        }
        guard !host.isEmpty, host.count <= 253 else { return nil }
        let allowed = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyz0123456789.-")
        guard host.unicodeScalars.allSatisfy({ allowed.contains($0) }) else { return nil }
        guard !host.hasPrefix("."), !host.hasSuffix("."), !host.contains("..") else { return nil }

        let trimmed = code.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let hexadecimal = CharacterSet(charactersIn: "0123456789abcdef")
        guard trimmed.isEmpty || (trimmed.count == 8 && trimmed.unicodeScalars.allSatisfy({ hexadecimal.contains($0) })) else { return nil }
        return ServerSettings(host: host, port: port, code: trimmed)
    }

    static func load() -> ServerSettings? {
        guard let data = UserDefaults.standard.data(forKey: storageKey) else { return nil }
        return try? JSONDecoder().decode(ServerSettings.self, from: data)
    }

    func save() {
        guard let data = try? JSONEncoder().encode(self) else { return }
        UserDefaults.standard.set(data, forKey: Self.storageKey)
    }

    static func forget() {
        UserDefaults.standard.removeObject(forKey: storageKey)
    }
}
