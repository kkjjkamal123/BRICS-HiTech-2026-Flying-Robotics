import AppKit
import CoreImage

/// The TR256i thermal camera sends a 256 x 384 frame: the top half is the picture, the bottom half is raw
/// temperature data that looks like green noise once it has been through the drone's camera driver.
/// This keeps the picture half, stretches its contrast and (optionally) paints it with an iron palette so hot
/// things stand out.
@MainActor
enum ThermalFrame {
    private static let context = CIContext(options: [.cacheIntermediates: false])
    private static var low: CGFloat = 0, high: CGFloat = 1     // smoothed black / white points (no flicker)

    static func isThermal(_ image: CGImage) -> Bool { image.width == 256 && image.height == 384 }

    static func cgImage(from data: Data) -> CGImage? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }
        return CGImageSourceCreateImageAtIndex(source, 0, nil)
    }

    /// Picture half only, contrast stretched; `palette` false = white-hot greyscale.
    static func render(_ frame: CGImage, palette: Bool) -> NSImage? {
        guard let top = frame.cropping(to: CGRect(x: 0, y: 0, width: frame.width, height: frame.height / 2)) else { return nil }
        var image = CIImage(cgImage: top)
        let extent = image.extent

        // black / white points of this frame (1 x 1 result: r = min, g = max of luminance)
        if let filter = CIFilter(name: "CIAreaMinMaxRed", parameters: [kCIInputImageKey: image,
                                                                         kCIInputExtentKey: CIVector(cgRect: extent)]),
           let out = filter.outputImage {
            var px = [UInt8](repeating: 0, count: 4)
            context.render(out, toBitmap: &px, rowBytes: 4, bounds: CGRect(x: 0, y: 0, width: 1, height: 1),
                           format: .RGBA8, colorSpace: nil)
            let lo = CGFloat(px[0]) / 255, hi = max(CGFloat(px[1]) / 255, CGFloat(px[0]) / 255 + 0.08)
            low += (lo - low) * 0.15
            high += (hi - high) * 0.15
        }
        let gain = 1 / max(0.05, high - low)
        image = image.applyingFilter("CIColorMatrix", parameters: [
            "inputRVector": CIVector(x: gain, y: 0, z: 0, w: 0),
            "inputGVector": CIVector(x: 0, y: gain, z: 0, w: 0),
            "inputBVector": CIVector(x: 0, y: 0, z: gain, w: 0),
            "inputBiasVector": CIVector(x: -low * gain, y: -low * gain, z: -low * gain, w: 0)])
            .applyingFilter("CIColorClamp")
        if palette, let gradient = ironGradient {
            image = image.applyingFilter("CIColorMap", parameters: ["inputGradientImage": gradient])
        }
        guard let cg = context.createCGImage(image, from: extent) else { return nil }
        return NSImage(cgImage: cg, size: NSSize(width: cg.width, height: cg.height))
    }

    /// cold -> hot: black, violet, red, orange, yellow, white
    private static let ironGradient: CIImage? = {
        let stops: [(CGFloat, CGFloat, CGFloat)] = [(0, 0, 0.04), (0.28, 0.0, 0.45), (0.78, 0.10, 0.25), (1.0, 0.45, 0.0),
                                                    (1.0, 0.85, 0.15), (1, 1, 1)]
        let space = CGColorSpaceCreateDeviceRGB()
        guard let ctx = CGContext(data: nil, width: 256, height: 1, bitsPerComponent: 8, bytesPerRow: 0, space: space,
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue),
              let gradient = CGGradient(colorsSpace: space,
                                        colors: stops.map { CGColor(red: $0.0, green: $0.1, blue: $0.2, alpha: 1) } as CFArray,
                                        locations: nil) else { return nil }
        ctx.drawLinearGradient(gradient, start: .zero, end: CGPoint(x: 256, y: 0), options: [])
        return ctx.makeImage().map { CIImage(cgImage: $0) }
    }()
}
