// media_export —— 把 ProRes 母版按裁框+目标尺寸转成 H.265/H.264（社媒版）。
//
// 用法:
//   media_export --probe <src>                          # 打印母版尺寸 "W H"
//   media_export <src> <out> <hevc|h264> <cx> <cy> <cw> <ch> <ow> <oh>
//
// 裁框(cx,cy,cw,ch) 由 Python 中心裁算好；这里只把该区域映射到 ow×oh 输出。
// 用 AVAssetExportSession + AVMutableVideoComposition：renderSize=输出尺寸，
// layerInstruction transform = 平移(-裁原点) 再缩放(输出/裁框)。

import AVFoundation
import Foundation

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(1)
}

let args = CommandLine.arguments

// --probe 模式
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

guard args.count == 10 else {
    fail("用法: media_export <src> <out> <hevc|h264> <cx> <cy> <cw> <ch> <ow> <oh>")
}
let src = args[1], outPath = args[2], fmt = args[3]
let cx = Double(args[4])!, cy = Double(args[5])!, cw = Double(args[6])!, ch = Double(args[7])!
let ow = Int(args[8])!, oh = Int(args[9])!

let preset: String
switch fmt {
case "hevc": preset = AVAssetExportPresetHEVCHighestQuality
case "h264": preset = AVAssetExportPresetHighestQuality
default: fail("未知格式: \(fmt)")
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
    let sx = Double(ow) / cw, sy = Double(oh) / ch
    let transform = CGAffineTransform(translationX: -cx, y: -cy)
        .concatenating(CGAffineTransform(scaleX: sx, y: sy))
    layer.setTransform(transform, at: .zero)
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
