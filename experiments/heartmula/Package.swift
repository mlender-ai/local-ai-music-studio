// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "HeartStudy",
    platforms: [.macOS(.v26)],
    dependencies: [
        .package(url: "https://github.com/xocialize/mlx-heartmula-swift", revision: "286ec73dce44f8d470d85ae7ad1db000feac5e06"),
        .package(url: "https://github.com/ml-explore/mlx-swift", exact: "0.32.3")
    ],
    targets: [.executableTarget(name: "HeartStudy", dependencies: [
        .product(name: "HeartMuLaCore", package: "mlx-heartmula-swift"),
        .product(name: "MLX", package: "mlx-swift"),
        .product(name: "MLXRandom", package: "mlx-swift"),
        .product(name: "MLXNN", package: "mlx-swift")
    ], swiftSettings: [.swiftLanguageMode(.v5)])]
)
