// mov_concat —— 把同编码 ProRes 片段按序无损拼接成单个 MOV。
//
// 用法: mov_concat <output.mov> <chunk1.mov> <chunk2.mov> ...
//
// 用 AVFoundation 的 AVAssetExportPresetPassthrough：只重排容器、不重编码，
// 因此各 chunk 必须同编码/同分辨率/同帧率（AE 分块渲染天然满足）。
// 由 pipeline/ae.py 在 AE 阶段渲染完分块后调用，产出 _ae_intermediate.mov 供 PR 阶段消费。

import AVFoundation
import Foundation

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(1)
}

let args = CommandLine.arguments
guard args.count >= 3 else {
    FileHandle.standardError.write("用法: mov_concat <output> <chunk...>\n".data(using: .utf8)!)
    exit(2)
}
let outputPath = args[1]
let inputs = Array(args[2...])

let composition = AVMutableComposition()
guard let videoTrack = composition.addMutableTrack(
    withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid) else {
    fail("无法创建视频轨")
}

var cursor = CMTime.zero
do {
    for path in inputs {
        let asset = AVURLAsset(url: URL(fileURLWithPath: path))
        let vtracks = try await asset.loadTracks(withMediaType: .video)
        let dur = try await asset.load(.duration)
        guard let src = vtracks.first else { fail("片段无视频轨: \(path)") }
        try videoTrack.insertTimeRange(
            CMTimeRange(start: .zero, duration: dur), of: src, at: cursor)
        cursor = CMTimeAdd(cursor, dur)
    }
} catch {
    fail("拼接失败: \(error.localizedDescription)")
}

let outURL = URL(fileURLWithPath: outputPath)
try? FileManager.default.removeItem(at: outURL)
guard let export = AVAssetExportSession(
    asset: composition, presetName: AVAssetExportPresetPassthrough) else {
    fail("无法创建导出会话")
}
export.outputURL = outURL
export.outputFileType = .mov

await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
    export.exportAsynchronously { cont.resume() }
}

if export.status == .completed {
    exit(0)
} else {
    fail("导出失败: \(export.error?.localizedDescription ?? "未知错误")")
}
