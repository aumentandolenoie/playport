// SPDX-License-Identifier: GPL-3.0-or-later
// Optional per-device private GitHub storage for player-generated report ZIPs.
// No repository token is ever compiled into the IPA or stored in UserDefaults.
import Foundation
import Security
import UIKit

@MainActor
enum PrivateReportUpload {
    private static let service = "dev.playport.private-report-upload"
    private static let tokenAccount = "github-fine-grained-token"
    private static let repositoryKey = "privateReportRepository"
    private static let enabledKey = "privateReportUploadEnabled"
    private static let maxBytes = 20 * 1024 * 1024

    private static func token() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: tokenAccount,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private static func saveToken(_ token: String) -> Bool {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: tokenAccount
        ]
        SecItemDelete(query as CFDictionary)
        let values: [String: Any] = query.merging([
            kSecValueData as String: Data(token.utf8),
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        ]) { _, new in new }
        return SecItemAdd(values as CFDictionary, nil) == errSecSuccess
    }

    private static func topController() -> UIViewController? {
        guard let scene = UIApplication.shared.connectedScenes
            .compactMap({ $0 as? UIWindowScene })
            .first(where: { $0.activationState == .foregroundActive }) else { return nil }
        var controller = scene.keyWindow?.rootViewController
        while let next = controller?.presentedViewController { controller = next }
        return controller
    }

    private static func message(_ title: String, _ text: String) {
        guard let controller = topController() else { return }
        let alert = UIAlertController(title: title, message: text, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default))
        controller.present(alert, animated: true)
    }

    /// Initial setup is always explicit, and can be disabled or reconfigured.
    static func configure() {
        guard let controller = topController() else { return }
        let alert = UIAlertController(
            title: "Private log archive",
            message: "Create a PRIVATE GitHub repository. Enter owner/repository and a fine-grained GitHub token with Contents: Read and write access ONLY to that repository. Reports may include private account and device data. Once enabled, every Report a problem ZIP uploads automatically.",
            preferredStyle: .alert
        )
        alert.addTextField { field in
            field.placeholder = "owner/private-reports"
            field.text = UserDefaults.standard.string(forKey: repositoryKey)
            field.autocapitalizationType = .none
            field.autocorrectionType = .no
        }
        alert.addTextField { field in
            field.placeholder = "Fine-grained GitHub token"
            field.isSecureTextEntry = true
            field.autocapitalizationType = .none
            field.autocorrectionType = .no
        }
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel))
        alert.addAction(UIAlertAction(title: "Disable and clear token", style: .destructive) { _ in
            UserDefaults.standard.removeObject(forKey: repositoryKey)
            UserDefaults.standard.set(false, forKey: enabledKey)
            let query: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: service,
                kSecAttrAccount as String: tokenAccount
            ]
            SecItemDelete(query as CFDictionary)
        })
        alert.addAction(UIAlertAction(title: "Enable", style: .default) { _ in
            let repository = alert.textFields?[0].text?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let credential = alert.textFields?[1].text?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let pieces = repository.split(separator: "/", omittingEmptySubsequences: false)
            let valid = pieces.count == 2 && pieces.allSatisfy {
                !$0.isEmpty && $0.range(of: #"^[A-Za-z0-9_.-]+$"#, options: .regularExpression) != nil
            }
            guard valid, !credential.isEmpty else {
                message("Not configured", "Provide owner/repository and a token. Nothing was uploaded.")
                return
            }
            guard saveToken(credential) else {
                message("Not configured", "Could not securely store the GitHub token.")
                return
            }
            // Enabling is pending until GitHub confirms the destination is private.
            UserDefaults.standard.set(false, forKey: enabledKey)
            Task {
                do {
                    try await validatePrivateRepository(repository: repository, token: credential)
                    UserDefaults.standard.set(repository, forKey: repositoryKey)
                    UserDefaults.standard.set(true, forKey: enabledKey)
                    message("Private archive enabled", "Future Report a problem ZIPs will upload automatically. The normal iOS share sheet remains available.")
                } catch {
                    let query: [String: Any] = [
                        kSecClass as String: kSecClassGenericPassword,
                        kSecAttrService as String: service,
                        kSecAttrAccount as String: tokenAccount
                    ]
                    SecItemDelete(query as CFDictionary)
                    message("Not configured", "GitHub privacy/access verification failed: \(error.localizedDescription)")
                }
            }
        })
        controller.present(alert, animated: true)
    }

    private static func request(_ url: URL, token: String, method: String = "GET", body: Data? = nil) async throws -> (Data, HTTPURLResponse) {
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        req.setValue("2022-11-28", forHTTPHeaderField: "X-GitHub-Api-Version")
        req.timeoutInterval = 45
        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = body
        }
        let (data, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse else { throw UploadError.badResponse }
        return (data, http)
    }

    private static func validatePrivateRepository(repository: String, token: String) async throws {
        guard let url = URL(string: "https://api.github.com/repos/\(repository)") else { throw UploadError.badResponse }
        let (data, response) = try await request(url, token: token)
        guard response.statusCode == 200,
              let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              json["private"] as? Bool == true else { throw UploadError.notPrivate }
    }

    static func uploadIfEnabled(_ zip: URL, gameID: String) async {
        guard UserDefaults.standard.bool(forKey: enabledKey),
              let repository = UserDefaults.standard.string(forKey: repositoryKey),
              let credential = token() else { return }
        do {
            try await validatePrivateRepository(repository: repository, token: credential)
            let bytes = try Data(contentsOf: zip)
            guard bytes.count <= maxBytes else { throw UploadError.tooLarge }
            let safeID = String(gameID.map { $0.isLetter || $0.isNumber || $0 == "-" ? $0 : "_" })
            let filename = zip.lastPathComponent
            guard filename.hasPrefix("Playport-report-"), filename.hasSuffix(".zip") else {
                throw UploadError.badResponse
            }
            let components = [safeID, filename].map {
                $0.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? $0
            }
            guard let url = URL(string: "https://api.github.com/repos/\(repository)/contents/reports/\(components[0])/\(components[1])") else {
                throw UploadError.badResponse
            }
            let body = try JSONSerialization.data(withJSONObject: [
                "message": "Archive private Playport report \(safeID)",
                "content": bytes.base64EncodedString()
            ])
            let (_, response) = try await request(url, token: credential, method: "PUT", body: body)
            guard response.statusCode == 201 else { throw UploadError.uploadFailed(response.statusCode) }
            LibraryModel.log("private report upload: successful for \(safeID)")
        } catch {
            // Do not log the token, ZIP contents, credentials or server response body.
            LibraryModel.log("private report upload: failed for \(gameID): \(error.localizedDescription)")
            message("Log upload failed", "The report was not uploaded (\(error.localizedDescription)). You can still share its ZIP normally.")
        }
    }

    enum UploadError: LocalizedError {
        case badResponse, notPrivate, tooLarge, uploadFailed(Int)
        var errorDescription: String? {
            switch self {
            case .badResponse: "Invalid GitHub request or response."
            case .notPrivate: "Repository is not private or your token cannot access it."
            case .tooLarge: "Report exceeds the 20 MB private upload limit."
            case .uploadFailed(let status): "GitHub rejected the upload (HTTP \(status))."
            }
        }
    }
}
