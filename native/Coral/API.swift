import Foundation
import Security
import CryptoKit
import AuthenticationServices
import SwiftUI

enum APIError: LocalizedError {
    case message(String)
    var errorDescription: String? { if case let .message(text) = self { return text }; return nil }
}

enum Keychain {
    static func read(_ key: String) -> String? {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "com.coral.workspace", kSecAttrAccount as String: key,
            kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
    static func save(_ value: String?, key: String) throws {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "com.coral.workspace", kSecAttrAccount as String: key]
        SecItemDelete(query as CFDictionary)
        if let value {
            var entry = query
            entry[kSecValueData as String] = Data(value.utf8)
            entry[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            let status = SecItemAdd(entry as CFDictionary, nil)
            if status != errSecSuccess { throw APIError.message("Could not store your session securely (Keychain \(status)).") }
        }
    }
}

@MainActor
final class API {
    var baseURL: String
    var token: String? { didSet { try? Keychain.save(token, key: baseURL) } }
    let decoder: JSONDecoder = { let d = JSONDecoder(); d.keyDecodingStrategy = .convertFromSnakeCase; return d }()

    init(baseURL: String) {
        self.baseURL = baseURL.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        self.token = Keychain.read(self.baseURL)
    }

    func request<T: Decodable>(_ path: String, method: String = "GET", body: [String: Any]? = nil,
                               key: String? = nil) async throws -> T {
        let data = try await raw(path, method: method, body: body, key: key)
        return try decoder.decode(T.self, from: data)
    }

    func raw(_ path: String, method: String = "GET", body: [String: Any]? = nil, key: String? = nil) async throws -> Data {
        guard let url = URL(string: baseURL + path), let scheme = url.scheme,
              scheme == "https" || (scheme == "http" && ["127.0.0.1", "localhost", "::1"].contains(url.host ?? "")) else {
            throw APIError.message("Use an HTTPS backend URL, or localhost for development.")
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = path.hasSuffix("/connect") ? 600 : 45
        if let token { request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
        if let key { request.setValue(key, forHTTPHeaderField: "Idempotency-Key") }
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw APIError.message("No response from Coral.") }
        guard (200..<300).contains(response.statusCode) else {
            if response.statusCode == 401 { token = nil }
            let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            throw APIError.message(json?["detail"] as? String ?? "Request failed (\(response.statusCode)).")
        }
        return data
    }
}

@MainActor
final class GitHubSignIn: NSObject, ASWebAuthenticationPresentationContextProviding {
    private var session: ASWebAuthenticationSession?
    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        #if os(macOS)
        return NSApplication.shared.keyWindow ?? NSApplication.shared.windows.first ?? ASPresentationAnchor()
        #else
        return UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.flatMap(\.windows).first { $0.isKeyWindow } ?? ASPresentationAnchor()
        #endif
    }
    func signIn(api: API, link: Bool = false) async throws {
        var bytes = [UInt8](repeating: 0, count: 32)
        guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else { throw APIError.message("Could not initialize secure sign-in.") }
        func base64(_ data: Data) -> String { data.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
        let verifier = base64(Data(bytes))
        let challenge = base64(Data(SHA256.hash(data: Data(verifier.utf8))))
        let prepared: URLResponse = try await api.request("/auth/prepare", method: "POST", body: ["challenge": challenge, "client": "native", "link_account": link])
        guard let url = URL(string: prepared.url) else { throw APIError.message("Invalid sign-in URL.") }
        let callback: URL = try await withCheckedThrowingContinuation { continuation in
            session = ASWebAuthenticationSession(url: url, callbackURLScheme: "coral") { callback, error in
                if let callback { continuation.resume(returning: callback) }
                else { continuation.resume(throwing: error ?? APIError.message("Sign-in cancelled.")) }
            }
            session?.presentationContextProvider = self
            session?.prefersEphemeralWebBrowserSession = true
            if session?.start() != true { continuation.resume(throwing: APIError.message("Could not open GitHub sign-in.")) }
        }
        let query = URLComponents(url: callback, resolvingAgainstBaseURL: false)?.queryItems
        guard let code = query?.first(where: { $0.name == "code" })?.value else {
            throw APIError.message(query?.first(where: { $0.name == "error" })?.value ?? "GitHub sign-in did not return a code.")
        }
        let response: TokenResponse = try await api.request("/auth/exchange", method: "POST", body: ["code": code, "verifier": verifier])
        try Keychain.save(response.token, key: api.baseURL)
        api.token = response.token
        session = nil
    }
}
