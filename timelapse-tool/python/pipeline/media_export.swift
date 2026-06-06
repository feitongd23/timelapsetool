// media_export —— 把 ProRes 母版转成 H.265/H.264 社媒版，支持运镜（裁框随时间渐变）。
//
// 用法:
//   media_export --probe <src>        # 打印母版尺寸 "W H"
//   media_export --saliency <src>     # 打印主体中心（Vision 显著性）归一化 "cx cy"
//   media_export <src> <out> <hevc|h264> <sx sy sw sh> <ex ey ew eh> <ow oh>
//
// 起止两个裁框由 Python 算好（运镜=起≠止；无运镜=起=止）。这里用
// AVMutableVideoComposition.renderSize=输出尺寸 + layerInstruction 的 transform ramp
// 从「起始框→输出」过渡到「结束框→输出」。

import AVFoundation
import Foundation
import Vision
import CoreImage
import ImageIO

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(1)
}

let args = CommandLine.arguments

// --probe：母版像素尺寸
if args.count == 3 && args[1] == "--probe" {
    let asset = AVURLAsset(url: URL(fileURLWithPath: args[2]))
    let sem = DispatchSemaphore(value: 0)
    Task {
        guard let t = try? await asset.loadTracks(withMediaType: .video).first,
              let size = try? await t.load(.naturalSize) else { fail("无法读取母版尺寸") }
        print("\(Int(abs(size.width))) \(Int(abs(size.height)))")
        sem.signal()
    }
    sem.wait()
    exit(0)
}

// --saliency：抽中间帧跑 Vision 显著性，输出主体中心（归一化，左上原点口径）
if args.count == 3 && args[1] == "--saliency" {
    let asset = AVURLAsset(url: URL(fileURLWithPath: args[2]))
    let sem = DispatchSemaphore(value: 0)
    Task {
        var cx = 0.5, cy = 0.5
        let dur = (try? await asset.load(.duration)) ?? .zero
        let gen = AVAssetImageGenerator(asset: asset)
        gen.appliesPreferredTrackTransform = true
        let mid = CMTime(seconds: max(0, CMTimeGetSeconds(dur) / 2), preferredTimescale: 600)
        if let cg = try? gen.copyCGImage(at: mid, actualTime: nil) {
            let req = VNGenerateAttentionBasedSaliencyImageRequest()
            let handler = VNImageRequestHandler(cgImage: cg, options: [:])
            if (try? handler.perform([req])) != nil,
               let obs = req.results?.first as? VNSaliencyImageObservation,
               let salient = obs.salientObjects?.first {
                cx = Double(salient.boundingBox.midX)
                cy = 1.0 - Double(salient.boundingBox.midY)   // Vision 原点左下 → 翻成左上
            }
        }
        print("\(cx) \(cy)")
        sem.signal()
    }
    sem.wait()
    exit(0)
}

// --saturation：从一批图里挑平均饱和度最高的（打印其路径）。支持 RAW/JPG/TIF。
if args.count >= 3 && args[1] == "--saturation" {
    let files = Array(args[2...])
    let ctx = CIContext(options: nil)
    var best = files.first ?? "", bestS = -1.0
    for f in files {
        guard let img = CIImage(contentsOf: URL(fileURLWithPath: f)) else { continue }
        let extent = img.extent
        guard extent.width > 0, extent.height > 0,
              let avgF = CIFilter(name: "CIAreaAverage", parameters: [
                  kCIInputImageKey: img, kCIInputExtentKey: CIVector(cgRect: extent)]),
              let avg = avgF.outputImage else { continue }
        var px = [UInt8](repeating: 0, count: 4)
        ctx.render(avg, toBitmap: &px, rowBytes: 4,
                   bounds: CGRect(x: 0, y: 0, width: 1, height: 1),
                   format: .RGBA8, colorSpace: CGColorSpaceCreateDeviceRGB())
        let r = Double(px[0]), g = Double(px[1]), b = Double(px[2])
        let mx = max(r, g, b), mn = min(r, g, b)
        let s = mx == 0 ? 0 : (mx - mn) / mx
        if s > bestS { bestS = s; best = f }
    }
    print(best)
    exit(0)
}

// --meta：读 RAW/图片的相机/拍摄/分辨率元数据，输出 JSON。
if args.count == 3 && args[1] == "--meta" {
    var out: [String: Any] = [:]
    if let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: args[2]) as CFURL, nil),
       let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any] {
        if let w = props[kCGImagePropertyPixelWidth] as? Int { out["width"] = w }
        if let h = props[kCGImagePropertyPixelHeight] as? Int { out["height"] = h }
        if let tiff = props[kCGImagePropertyTIFFDictionary] as? [CFString: Any] {
            if let m = tiff[kCGImagePropertyTIFFModel] as? String { out["camera"] = m }
            if let mk = tiff[kCGImagePropertyTIFFMake] as? String { out["make"] = mk }
        }
        if let exif = props[kCGImagePropertyExifDictionary] as? [CFString: Any] {
            if let e = exif[kCGImagePropertyExifExposureTime] as? Double { out["exposure"] = e }
            if let f = exif[kCGImagePropertyExifFNumber] as? Double { out["fnumber"] = f }
            if let iso = exif[kCGImagePropertyExifISOSpeedRatings] as? [Int], let i = iso.first { out["iso"] = i }
            if let fl = exif[kCGImagePropertyExifFocalLength] as? Double { out["focal"] = fl }
            if let lens = exif[kCGImagePropertyExifLensModel] as? String { out["lens"] = lens }
        }
    }
    if let data = try? JSONSerialization.data(withJSONObject: out),
       let s = String(data: data, encoding: .utf8) { print(s) } else { print("{}") }
    exit(0)
}

guard args.count == 14 else {
    fail("用法: media_export <src> <out> <hevc|h264> <sx sy sw sh> <ex ey ew eh> <ow oh>")
}
let src = args[1], outPath = args[2], fmt = args[3]
let sx0 = Double(args[4])!, sy0 = Double(args[5])!, sw0 = Double(args[6])!, sh0 = Double(args[7])!
let ex0 = Double(args[8])!, ey0 = Double(args[9])!, ew0 = Double(args[10])!, eh0 = Double(args[11])!
let ow = Int(args[12])!, oh = Int(args[13])!

let preset: String
switch fmt {
case "hevc": preset = AVAssetExportPresetHEVCHighestQuality
case "h264": preset = AVAssetExportPresetHighestQuality
default: fail("未知格式: \(fmt)")
}

// 把母版里的裁框 (x,y,w,h) 映射到 ow×oh 输出的 transform
func cropTransform(_ x: Double, _ y: Double, _ w: Double, _ h: Double) -> CGAffineTransform {
    CGAffineTransform(translationX: -x, y: -y)
        .concatenating(CGAffineTransform(scaleX: Double(ow) / w, y: Double(oh) / h))
}

let asset = AVURLAsset(url: URL(fileURLWithPath: src))
let done = DispatchSemaphore(value: 0)
Task {
    guard let track = try? await asset.loadTracks(withMediaType: .video).first else {
        fail("母版无视频轨")
    }
    let fps = (try? await track.load(.nominalFrameRate)) ?? 60

    let vc = AVMutableVideoComposition()
    vc.renderSize = CGSize(width: ow, height: oh)
    vc.frameDuration = CMTime(value: 1, timescale: CMTimeScale(fps.rounded()))

    let instruction = AVMutableVideoCompositionInstruction()
    let dur = (try? await asset.load(.duration)) ?? .zero
    instruction.timeRange = CMTimeRange(start: .zero, duration: dur)

    let layer = AVMutableVideoCompositionLayerInstruction(assetTrack: track)
    let startT = cropTransform(sx0, sy0, sw0, sh0)
    let endT = cropTransform(ex0, ey0, ew0, eh0)
    // 起=止时为静止（无运镜）；起≠止时匀速运镜
    layer.setTransformRamp(fromStart: startT, toEnd: endT,
                           timeRange: CMTimeRange(start: .zero, duration: dur))
    instruction.layerInstructions = [layer]
    vc.instructions = [instruction]

    guard let export = AVAssetExportSession(asset: asset, presetName: preset) else {
        fail("无法创建导出会话")
    }
    let outURL = URL(fileURLWithPath: outPath)
    try? FileManager.default.removeItem(at: outURL)
    export.outputURL = outURL
    export.outputFileType = .mp4
    export.videoComposition = vc

    await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
        export.exportAsynchronously { c.resume() }
    }
    if export.status == .completed { done.signal() }
    else { fail("导出失败: \(export.error?.localizedDescription ?? "未知")") }
}
done.wait()
exit(0)
