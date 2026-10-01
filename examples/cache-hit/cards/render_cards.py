"""Render the cache example with the shared skill renderer."""

import importlib.util
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
TEMPLATE = REPO_ROOT / "skills/feynman-notes/templates/render_cards.py"
spec = importlib.util.spec_from_file_location("feynman_cards", TEMPLATE)
renderer = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(renderer)
renderer.SERIES = "看懂缓存"
renderer.SCRIPT_PATH = Path(__file__).resolve()
renderer.SCRIPT_DIR = SCRIPT_DIR
renderer.PNG_DIR = SCRIPT_DIR / "png"
renderer.WORKSPACE_ROOT = REPO_ROOT


# All semantic text and arrows share one collision-check group.
SCENE = renderer.SCENE_KIT + r"""
function label(y,text,size,color){
  return TFit(12,y,text,{'font-size':size||30,'font-weight':700,
    fill:color||'#2F3437'},
    {maxWidth:736,padding:24,minFontSize:26,align:'center',guardGroup:'scene'});
}
function arrow(y1,y2){ Guard(down(380,y1,y2),'connector','scene',16); }
"""


def build_episode(ctx):
    cards = [(
        renderer.card_name(ctx, "01_cover"),
        renderer.page(renderer.text_card(
            ctx, "",
            '<div class="ctitle"><div class="ln">同一道题</div>'
            '<div class="ln">为何能</div>'
            '<div class="ln last">少算一次？</div></div>'
            '<div class="cdefinition">把算过的结果存起来，<br>下次满足条件时直接取。</div>'
            '<div class="csub">缓存（cache）· 第 01 集<br>教学示意 · square(x) = x × x</div>',
        )),
    )]
    scenes = [
        (
            "02_miss", "02", "第一次：没找到，就算并存下",
            "把输入 <b>3</b> 当作查找用的标记（key）。缓存里还没有它。",
            SCENE + r"""
label(62,'① 查找输入 3',32);
R(90,112,580,124,18,'#FAF8F3','#B06A5A',3);
label(190,'缓存：空  →  未命中（miss）',32,'#9b5649');
arrow(265,315);
label(385,'② 执行 square(3)',32);
label(510,'3 × 3 = 9',64,'#5f6b50');
arrow(565,635);
label(700,'③ 返回 9，并保存对应关系',32);
R(90,730,580,146,18,'#e7ecdf','#7E8B6D',3);
label(822,'缓存：3 → 9',46,'#5f6b50');
teachingBadge(610,930);
""",
            '<p class="cap">这次计算没有省掉；它为下一次复用留下结果。</p>',
        ),
        (
            "03_hit", "03", "第二次：同样的 3，直接取 9",
            "规则和相关数据没变。再次查找 <b>3</b>，缓存中已有对应结果。",
            SCENE + r"""
label(62,'① 再次收到输入 3',32);
R(90,112,580,150,18,'#e7ecdf','#7E8B6D',3);
label(165,'缓存：3 → 9',46,'#5f6b50');
label(245,'找到可用结果：命中（hit）',28,'#5f6b50');
arrow(295,365);
label(425,'② 取出保存的 9',36);
label(585,'9',100,'#5f6b50');
arrow(650,715);
label(785,'③ 直接返回 9',36);
R(90,825,580,102,16,'#f2e2dc','#B06A5A',2);
label(890,'本次跳过：3 × 3',32,'#9b5649');
teachingBadge(610,975);
""",
            '<p class="cap">缓存命中省掉的是重复计算；查找缓存仍然需要工作。</p>',
        ),
        (
            "04_boundary", "04", "什么时候不能直接复用旧结果？",
            "输入要匹配；计算规则和相关数据也必须仍然适用。",
            SCENE + r"""
label(58,'输入变为 4：原来只有 3 → 9',32);
R(55,102,650,258,18,'#FAF8F3','#7E8B6D',2);
label(158,'查 4：没有对应条目',30,'#9b5649');
label(252,'4 × 4 = 16',46,'#5f6b50');
label(335,'返回 16；新增 4 → 16',30);
label(445,'规则改变：平方 square → 立方 cube',30);
R(55,490,650,330,18,'#FAF8F3','#B06A5A',2);
label(550,'再次输入 3，旧的 3 → 9 已失效',30,'#9b5649');
label(625,'先清空旧缓存，再按新规则算',30);
label(725,'3 × 3 × 3 = 27',46,'#5f6b50');
label(800,'返回 27；保存新的 3 → 27',28);
label(905,'相关数据变化，也可能让旧结果失效',29);
teachingBadge(610,960);
""",
            '<p class="cap">也可把规则版本放进 key，隔开新旧结果。实际系统需要明确失效条件。</p>',
        ),
    ]
    for slug, number, title, caption, scene, below in scenes:
        cards.append((
            renderer.card_name(ctx, slug),
            renderer.page(renderer.diagram_card(
                ctx, number, title, caption, "0 0 760 1020", scene, below,
                foot="教学示意 · 例子中的输入与结果可手算验证",
            )),
        ))
    return cards


renderer.EPISODES = {"01": {"subject": "缓存命中与失效", "builder": build_episode}}


if __name__ == "__main__":
    raise SystemExit(renderer.main())
