// AE 效果内省：新建合成+纯色图层，加上 Deflicker 与变形稳定器，
// 把它们的 matchName 与所有属性的 (name, matchName) 写到桌面 ae-introspect.txt
(function () {
    var comp = app.project.activeItem;
    if (!comp || !(comp instanceof CompItem)) {
        comp = app.project.items.addComp("introspect", 1920, 1080, 1, 5, 25);
    }
    var solid = comp.layers.addSolid([1, 1, 1], "probe", comp.width, comp.height, 1);
    var lines = [];

    function dumpEffect(addArg, labelText) {
        try {
            var fx = solid.property("ADBE Effect Parade").addProperty(addArg);
            lines.push("=== " + labelText + " => name=" + fx.name + " | matchName=" + fx.matchName + " ===");
            walk(fx, "  ");
        } catch (e) {
            lines.push("!! 无法添加 [" + addArg + "]: " + e.toString());
        }
    }

    // 递归列出属性与属性组（变形稳定器的参数是嵌套的）
    function walk(grp, indent) {
        for (var i = 1; i <= grp.numProperties; i++) {
            var p = grp.property(i);
            var line = indent + "[" + i + "] name=" + p.name + " | matchName=" + p.matchName;
            try { if (p.value !== undefined) line += " | value=" + p.value; } catch (ev) {}
            lines.push(line);
            if (p.numProperties && p.numProperties > 0) {
                walk(p, indent + "  ");
            }
        }
    }

    dumpEffect("ADBE SubspaceStabilizer", "Warp Stabilizer 变形稳定器");

    var f = new File("~/Desktop/ae-introspect.txt");
    f.open("w");
    f.write(lines.join("\n"));
    f.close();
    alert("已写出 ~/Desktop/ae-introspect.txt\n请把它的内容发给我。");
})();
