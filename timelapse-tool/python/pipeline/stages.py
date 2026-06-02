class Stage:
    """流水线阶段基类。子类设置 name / manual，并实现 run()。"""

    name = "Stage"
    manual = False

    def run(self, config, emit):
        """执行阶段。emit(str) 推送进度。抛异常表示失败。"""
        raise NotImplementedError


class BRStage(Stage):
    name = "BR"
    manual = False

    def run(self, config, emit):
        # 桩：真实实现（Bridge 套 ACR 预设）由后续计划替换
        emit("BR 阶段（桩）：批量套用 Camera Raw 预设")


class LRTStage(Stage):
    name = "LRT"
    manual = True  # 手动阶段：runner 跑到这里会暂停等用户

    def run(self, config, emit):
        # 手动阶段无自动动作；打开 LRT 的逻辑由后续计划补充
        emit("LRT 阶段：请在 LRTimelapse 中手动完成关键帧/去闪/导出序列")


class AEStage(Stage):
    name = "AE"
    manual = False

    def run(self, config, emit):
        # 桩：真实实现（aerender）由后续计划替换
        emit("AE 阶段（桩）：渲染图像序列为中间视频")


class PRStage(Stage):
    name = "PR"
    manual = False

    def run(self, config, emit):
        # 桩：真实实现（Premiere 导出）由后续计划替换
        emit("PR 阶段（桩）：导入、增稳、按规格导出成片")


def default_stages():
    return [BRStage(), LRTStage(), AEStage(), PRStage()]
