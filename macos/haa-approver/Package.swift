// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "HAAApprover",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "haa-approver", targets: ["HAAApprover"])],
    targets: [
        .executableTarget(name: "HAAApprover"),
        .testTarget(name: "HAAApproverTests", dependencies: ["HAAApprover"])
    ]
)
