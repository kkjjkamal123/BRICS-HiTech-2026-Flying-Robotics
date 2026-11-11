import SwiftUI

enum AppSection: String, CaseIterable, Identifiable, Hashable {
    case overview, mission, flightTests, simulation, results, spec, aiModel, economics, documents

    var id: String { rawValue }

    var title: String {
        switch self {
        case .overview: "Overview"
        case .mission: "Mission Control"
        case .flightTests: "Flight Tests"
        case .simulation: "Simulation"
        case .results: "Results"
        case .spec: "Judging Spec"
        case .aiModel: "AI Model"
        case .economics: "Economics"
        case .documents: "Documents"
        }
    }

    var subtitle: String {
        switch self {
        case .overview: "Project status at a glance"
        case .mission: "Live telemetry, camera, map and commands"
        case .flightTests: "Bench and flight scripts on the drone"
        case .simulation: "Real mission code against a simulated drone"
        case .results: "Flight logs, detections and evidence"
        case .spec: "C1–C7, modules and pre-test checklist"
        case .aiModel: "Dataset, training and NPU export"
        case .economics: "NPV, IRR, payback and alternatives"
        case .documents: "Deliverables for the expert panel"
        }
    }

    var symbol: String {
        switch self {
        case .overview: "square.grid.2x2.fill"
        case .mission: "dot.radiowaves.left.and.right"
        case .flightTests: "airplane.departure"
        case .simulation: "cube.transparent.fill"
        case .results: "chart.xyaxis.line"
        case .spec: "checkmark.seal.fill"
        case .aiModel: "brain.head.profile.fill"
        case .economics: "chart.pie.fill"
        case .documents: "doc.richtext.fill"
        }
    }

    var tint: Color {
        switch self {
        case .overview: .indigo
        case .mission: .orange
        case .flightTests: .cyan
        case .simulation: .purple
        case .results: .teal
        case .spec: .green
        case .aiModel: .pink
        case .economics: .yellow
        case .documents: .blue
        }
    }

    var shortcut: KeyEquivalent {
        switch self {
        case .overview: "1"
        case .mission: "2"
        case .flightTests: "3"
        case .simulation: "4"
        case .results: "5"
        case .spec: "6"
        case .aiModel: "7"
        case .economics: "8"
        case .documents: "9"
        }
    }

    enum Group: String, CaseIterable, Identifiable {
        case fly = "Fly", evidence = "Evidence", build = "Build"
        var id: String { rawValue }
        var sections: [AppSection] {
            switch self {
            case .fly: [.overview, .mission, .flightTests, .simulation]
            case .evidence: [.results, .spec]
            case .build: [.aiModel, .economics, .documents]
            }
        }
    }
}
