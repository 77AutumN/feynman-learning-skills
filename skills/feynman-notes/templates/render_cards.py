# -*- coding: utf-8 -*-
# MIT License
#
# Copyright (c) 2026 77AutumN
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
"""
feynman-notes · 知识卡生成器（可复制模板）
==========================================================================
把本文件复制到:
  content/learning-notes/<series-slug>/cards/render_cards.py

最快起步:
  1. 修改 SERIES。
  2. 把 build_starter_episode() 里的 3 张示例卡换成本节内容。
  3. python render_cards.py

同一系列增加 episode:
  1. 新建 build_episode_02(ctx)。
  2. 在 EPISODES 中注册 "02": {"subject": "...", "builder": build_episode_02}。
  3. python render_cards.py 02          # 单 episode
     python render_cards.py 01 02       # 多 episode
     python render_cards.py all         # 全部 episode

模板自带的是通用 SVG scene kit，不是默认叙事皮肤。Path / grid / bolt /
dial / lockIcon / ghostTrail / stageStamp / teachingBadge 可以复用；每一集
仍要依据 visual brief 重新设计对象、隐喻、阶段和因果镜头。

框内文字优先使用 TFit / TWrap / BoxText，显式传 maxWidth、padding 和
minFontSize。字号降到下限仍放不下会登记布局错误；每张卡截图前还会
检查 HTML 全局溢出、SVG viewBox、受控文字边界和 strict 碰撞，预检失败
不截图。自由文字 / 连接线用 Guard 登记同组互检，纯装饰用 Decor 标注。
"""

from __future__ import annotations

import binascii
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from datetime import datetime, timezone
from html import escape, unescape
from pathlib import Path
from typing import Callable


SCRIPT_PATH = Path(__file__).resolve()
SCRIPT_DIR = SCRIPT_PATH.parent
SERIES = "系列名"
TOTAL_TOKEN = "__CARD_TOTAL__"
DEFAULT_EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
DEFAULT_CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
DEFAULT_BROWSER = DEFAULT_CHROME if DEFAULT_CHROME.is_file() else DEFAULT_EDGE
MANIFEST_SCHEMA = "learning-card-set/v1"
MANIFEST_ARTIFACT_KIND = "learning_card_set"
VISUAL_BASELINE_V0 = {
    "canvas": {"width": 1080, "height": 1440},
    "output": {"width": 2160, "height": 2880},
    "background": "#FAF8F3",
    "primary_color": "#7E8B6D",
    "negative_color": "#B06A5A",
    "border_color": "#E7E1D6",
    "cover_background": "#F4F3EF",
    "cover_accent": "#D63A2F",
    "font_system": "正文无衬线；公式与数字等宽",
    "whitespace": "clean",
    "subject_size": "medium",
    "paper_texture": "none",
    "graphic_language": "technical-diagram",
}
def find_skill_dir() -> Path:
    """Locate the bundled assets in a clone, local skill install, or user install."""
    explicit = os.environ.get("FEYNMAN_NOTES_SKILL_DIR")
    if explicit:
        candidates = [Path(explicit).expanduser().resolve()]
    else:
        candidates = [Path(__file__).resolve().parent.parent]
        starts = [SCRIPT_DIR, Path.cwd().resolve()]
        workspace = os.environ.get("FEYNMAN_NOTES_WORKSPACE_ROOT")
        if workspace:
            starts.insert(0, Path(workspace).expanduser().resolve())
        for start in starts:
            for root in (start, *start.parents):
                for prefix in ("skills", ".agents/skills", ".codex/skills"):
                    candidates.append(root / prefix / "feynman-notes")
        candidates.extend([
            Path.home() / ".agents/skills/feynman-notes",
            Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
            / "skills/feynman-notes",
        ])
    for candidate in dict.fromkeys(candidates):
        if (candidate / "assets/fonts/notosanssc.ttf").is_file() and (
            candidate / "schemas/card-manifest.schema.json"
        ).is_file():
            return candidate
    raise SystemExit(
        "找不到 feynman-notes 的字体和 schema。请完整安装技能，或设置 "
        "FEYNMAN_NOTES_SKILL_DIR 为技能目录。"
    )


SKILL_DIR = find_skill_dir()
WORKSPACE_ROOT = Path(os.environ.get("FEYNMAN_NOTES_WORKSPACE_ROOT", ".")).resolve()
FONT_PATH = SKILL_DIR / "assets/fonts/notosanssc.ttf"
CARD_MANIFEST_SCHEMA_PATH = SKILL_DIR / "schemas/card-manifest.schema.json"
FONT_URI = FONT_PATH.as_uri()
PNG_DIR = SCRIPT_DIR / "png"
BROWSER = Path(os.environ.get("FEYNMAN_NOTES_EDGE", str(DEFAULT_BROWSER)))


CARD_CSS = r"""
@font-face{font-family:'CoverHeavy';src:url('__FONT__') format('truetype');
  font-weight:100 900;font-display:block}
html,body{margin:0;padding:0}
.card{width:1080px;height:1440px;background:#FAF8F3;color:#2F3437;overflow:hidden;
  font-family:"CoverHeavy","Microsoft YaHei",sans-serif;box-sizing:border-box;
  padding:52px 56px;display:flex;flex-direction:column}
.top{display:flex;justify-content:space-between;align-items:center;
  font-size:24px;color:#a8a293;letter-spacing:.06em}
.top .series{color:#7E8B6D;font-weight:700;letter-spacing:.10em}
.hr{height:1px;background:#e7e1d6;margin:18px 0 6px}
h1{font-size:44px;font-weight:750;line-height:1.28;margin:12px 0 2px;color:#2F3437}
.cap{font-size:25px;color:#6b6b6b;line-height:1.68;margin:14px 2px}
.cap b{color:#5f6b50}.cap .bad{color:#b06a5a;font-weight:700}
.diagram{flex:1;display:flex;align-items:center;justify-content:center;min-height:0}
.diagram svg{width:100%;height:auto;max-height:100%;display:block}
.foot{font-size:21px;color:#bcb6a8;margin-top:8px;letter-spacing:.04em}
.cover{background:#F4F3EF;align-items:center;justify-content:center;
  text-align:center;padding:90px 80px}
.cover .ctitle{font-family:'CoverHeavy','Microsoft YaHei',sans-serif;
  font-weight:900;color:#161616}
.cover .ctitle .ln{font-size:126px;line-height:1.04;letter-spacing:-1px}
.cover .ctitle .smallline{font-size:102px}
.cover .ctitle .last{position:relative;display:inline-block;padding-bottom:4px}
.cover .ctitle .last::after{content:'';position:absolute;left:10%;right:10%;
  bottom:-18px;height:9px;background:#D63A2F;border-radius:5px}
.cover .cdefinition{font-family:"Microsoft YaHei",sans-serif;font-size:34px;
  color:#5f6b50;margin-top:54px;line-height:1.55;max-width:860px}
.cover .csub{font-family:"Microsoft YaHei",sans-serif;font-size:32px;
  color:#8A857C;margin-top:64px;letter-spacing:2px;line-height:1.65}
.tcard h1{margin-bottom:6px}
.fill{flex:1;display:flex;flex-direction:column;justify-content:center}
.note{border-left:4px solid #7E8B6D;padding:8px 0 8px 28px;margin:26px 0;
  font-size:30px;line-height:1.7;color:#3D4144}
.note.warn{border-left-color:#b06a5a}
.item{font-size:29px;line-height:1.52;margin:21px 0;color:#3D4144}
.item b{color:#2F3437}.item .d{display:block;font-size:25px;color:#6b6b6b;
  margin-top:5px}
.small{font-size:23px;color:#8a857c;line-height:1.7;margin-top:18px}
""".replace("__FONT__", FONT_URI)


LAYOUT_PREFLIGHT_JS = r"""
<script>
(() => {
  const report = document.createElement('pre');
  report.id = 'layout-preflight-report';
  report.hidden = true;
  document.body.appendChild(report);

  function mark(node, message) {
    if (!node) return;
    node.setAttribute('data-layout-error', message);
    if (node.namespaceURI === 'http://www.w3.org/2000/svg') {
      node.setAttribute('stroke', '#D63A2F');
      node.setAttribute('stroke-width', '2');
    } else {
      node.style.outline = '3px solid #D63A2F';
      node.style.outlineOffset = '-3px';
    }
  }

  function layoutNodeName(node) {
    const tag = (node.tagName || 'node').toLowerCase();
    const id = node.id ? `#${node.id}` : '';
    const label = node.getAttribute && (
      node.getAttribute('data-layout-label') ||
      node.textContent ||
      node.getAttribute('d') ||
      node.getAttribute('points')
    );
    const compact = String(label || '').replace(/\s+/g, ' ').trim().slice(0, 32);
    return `${tag}${id}${compact ? `[${compact}]` : ''}`;
  }

  function guardClearance(node) {
    const value = Number.parseFloat(node.getAttribute('data-layout-clearance'));
    return Number.isFinite(value) && value >= 0 ? value : 16;
  }

  function expandedBox(box, amount) {
    return {
      x: box.x - amount,
      y: box.y - amount,
      width: box.width + amount * 2,
      height: box.height + amount * 2,
    };
  }

  function boxesOverlap(a, b) {
    return (
      a.x < b.x + b.width &&
      a.x + a.width > b.x &&
      a.y < b.y + b.height &&
      a.y + a.height > b.y
    );
  }

  function pointInsideBox(point, box) {
    return (
      point.x >= box.x &&
      point.x <= box.x + box.width &&
      point.y >= box.y &&
      point.y <= box.y + box.height
    );
  }

  function isRenderedGuardCandidate(node) {
    const style = getComputedStyle(node);
    if (
      style.display === 'none' ||
      style.visibility === 'hidden' ||
      Number.parseFloat(style.opacity) === 0
    ) {
      return false;
    }
    if (node.tagName.toLowerCase() === 'text') {
      return Boolean(String(node.textContent || '').trim());
    }
    return true;
  }

  function connectorEntersBox(connector, box) {
    if (
      typeof connector.getTotalLength !== 'function' ||
      typeof connector.getPointAtLength !== 'function'
    ) {
      return false;
    }
    let length;
    try {
      length = connector.getTotalLength();
    } catch (error) {
      return false;
    }
    if (!Number.isFinite(length)) return false;
    const step = 4;
    for (let distance = 0; distance < length; distance += step) {
      if (pointInsideBox(connector.getPointAtLength(distance), box)) return true;
    }
    return pointInsideBox(connector.getPointAtLength(length), box);
  }

  function runStrictGuardPreflight(svg, svgIndex, add) {
    if (svg.getAttribute('data-layout-strict') !== 'true') return;
    const selector = 'text,line,path,polyline,polygon';
    const candidates = Array.from(svg.querySelectorAll(selector))
      .filter(isRenderedGuardCandidate);
    const guarded = [];

    candidates.forEach((node) => {
      if (node.getAttribute('data-layout-decoration') === 'true') return;
      const role = node.getAttribute('data-layout-role');
      const group = String(node.getAttribute('data-layout-group') || '').trim();
      const tag = node.tagName.toLowerCase();
      const expectedRole = tag === 'text' ? 'text' : 'connector';
      if (!role) {
        add(
          `STRICT_UNGUARDED svg=${svgIndex + 1} node=${layoutNodeName(node)}`,
          node
        );
        return;
      }
      if (role !== expectedRole) {
        add(
          `STRICT_ROLE_MISMATCH svg=${svgIndex + 1} node=${layoutNodeName(node)} ` +
          `expected=${expectedRole} actual=${role}`,
          node
        );
        return;
      }
      if (!group) {
        add(
          `STRICT_GROUP_MISSING svg=${svgIndex + 1} node=${layoutNodeName(node)}`,
          node
        );
        return;
      }
      guarded.push({node, role, group});
    });

    const byGroup = new Map();
    guarded.forEach((item) => {
      if (!byGroup.has(item.group)) byGroup.set(item.group, []);
      byGroup.get(item.group).push(item);
    });

    byGroup.forEach((items, group) => {
      const texts = items.filter((item) => item.role === 'text');
      const connectors = items.filter((item) => item.role === 'connector');
      for (let first = 0; first < texts.length; first += 1) {
        let firstBox;
        try {
          firstBox = texts[first].node.getBBox();
        } catch (error) {
          add(
            `GUARD_BBOX_FAILED group=${group} node=${layoutNodeName(texts[first].node)}`,
            texts[first].node
          );
          continue;
        }
        for (let second = first + 1; second < texts.length; second += 1) {
          let secondBox;
          try {
            secondBox = texts[second].node.getBBox();
          } catch (error) {
            add(
              `GUARD_BBOX_FAILED group=${group} ` +
              `node=${layoutNodeName(texts[second].node)}`,
              texts[second].node
            );
            continue;
          }
          const requiredGap = Math.max(
            guardClearance(texts[first].node),
            guardClearance(texts[second].node)
          );
          if (
            boxesOverlap(
              expandedBox(firstBox, requiredGap / 2),
              expandedBox(secondBox, requiredGap / 2)
            )
          ) {
            add(
              `TEXT_COLLISION group=${group} gap=${requiredGap} ` +
              `a=${layoutNodeName(texts[first].node)} ` +
              `b=${layoutNodeName(texts[second].node)}`,
              texts[first].node
            );
            mark(texts[second].node, `TEXT_COLLISION group=${group}`);
          }
        }

        connectors.forEach((connector) => {
          const requiredGap = Math.max(
            guardClearance(texts[first].node),
            guardClearance(connector.node)
          );
          const connectorSafetyBox = expandedBox(firstBox, requiredGap);
          if (connectorEntersBox(connector.node, connectorSafetyBox)) {
            add(
              `TEXT_CONNECTOR_COLLISION group=${group} gap=${requiredGap} ` +
              `text=${layoutNodeName(texts[first].node)} ` +
              `connector=${layoutNodeName(connector.node)}`,
              texts[first].node
            );
            mark(
              connector.node,
              `TEXT_CONNECTOR_COLLISION group=${group}`
            );
          }
        });
      }
    });
  }

  function runLayoutPreflight() {
    const errors = Array.from(window.__feynmanLayoutErrors || []);
    const add = (message, node) => {
      if (!errors.includes(message)) errors.push(message);
      mark(node, message);
    };
    const tolerance = 1.5;
    const html = document.documentElement;
    const body = document.body;

    if (html.scrollWidth > 1080 + tolerance || html.scrollHeight > 1440 + tolerance) {
      add(`HTML global overflow: ${html.scrollWidth}x${html.scrollHeight}`, html);
    }
    if (body.scrollWidth > 1080 + tolerance || body.scrollHeight > 1440 + tolerance) {
      add(`BODY global overflow: ${body.scrollWidth}x${body.scrollHeight}`, body);
    }
    document.querySelectorAll('.card').forEach((card, index) => {
      if (
        card.scrollWidth > card.clientWidth + tolerance ||
        card.scrollHeight > card.clientHeight + tolerance
      ) {
        add(
          `card ${index + 1} overflow: scroll ${card.scrollWidth}x${card.scrollHeight}, ` +
          `client ${card.clientWidth}x${card.clientHeight}`,
          card
        );
      }
    });

    document.querySelectorAll('svg').forEach((svg, index) => {
      const vb = svg.viewBox && svg.viewBox.baseVal;
      if (!vb || vb.width <= 0 || vb.height <= 0) {
        add(`svg ${index + 1} has no valid viewBox`, svg);
        return;
      }
      let box;
      try {
        box = svg.getBBox();
      } catch (error) {
        add(`svg ${index + 1} getBBox failed: ${error}`, svg);
        return;
      }
      if (
        box.x < vb.x - tolerance ||
        box.y < vb.y - tolerance ||
        box.x + box.width > vb.x + vb.width + tolerance ||
        box.y + box.height > vb.y + vb.height + tolerance
      ) {
        add(
          `svg ${index + 1} exceeds viewBox: bbox ` +
          `${box.x.toFixed(1)},${box.y.toFixed(1)},${box.width.toFixed(1)},` +
          `${box.height.toFixed(1)} vs viewBox ${vb.x},${vb.y},${vb.width},${vb.height}`,
          svg
        );
      }
    });

    document.querySelectorAll('[data-layout-controlled]').forEach((node, index) => {
      let box;
      try {
        box = node.getBBox();
      } catch (error) {
        add(`controlled text ${index + 1} getBBox failed: ${error}`, node);
        return;
      }
      const number = (name) => Number.parseFloat(node.getAttribute(name));
      const left = number('data-layout-left');
      const top = number('data-layout-top');
      const right = number('data-layout-right');
      const bottom = number('data-layout-bottom');
      if (Number.isFinite(left) && box.x < left - tolerance) {
        add(`controlled text ${index + 1} crosses left bound`, node);
      }
      if (Number.isFinite(top) && box.y < top - tolerance) {
        add(`controlled text ${index + 1} crosses top bound`, node);
      }
      if (Number.isFinite(right) && box.x + box.width > right + tolerance) {
        add(`controlled text ${index + 1} crosses right bound`, node);
      }
      if (Number.isFinite(bottom) && box.y + box.height > bottom + tolerance) {
        add(`controlled text ${index + 1} crosses bottom bound`, node);
      }
      const minSize = number('data-layout-min-font-size');
      const actualSize = Number.parseFloat(getComputedStyle(node).fontSize);
      if (Number.isFinite(minSize) && actualSize + 0.1 < minSize) {
        add(
          `controlled text ${index + 1} font ${actualSize}px is below minimum ${minSize}px`,
          node
        );
      }
      if (
        node.getAttribute('data-layout-controlled') === 'box-text' &&
        number('data-layout-padding') < 24
      ) {
        add(`controlled box text ${index + 1} padding is below 24 logical px`, node);
      }
    });

    document.querySelectorAll('svg').forEach((svg, index) => {
      runStrictGuardPreflight(svg, index, add);
    });

    const status = errors.length ? 'error' : 'ok';
    html.setAttribute('data-layout-status', status);
    report.setAttribute('data-layout-status', status);
    report.textContent = errors.join('\n');
  }

  const fontsReady = document.fonts ? document.fonts.ready : Promise.resolve();
  fontsReady
    .then(() => new Promise((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(resolve));
    }))
    .then(runLayoutPreflight)
    .catch((error) => {
      window.__feynmanLayoutErrors = window.__feynmanLayoutErrors || [];
      window.__feynmanLayoutErrors.push(`preflight crashed: ${error}`);
      runLayoutPreflight();
    });
  // 某些 Windows headless Edge 会暂停双 requestAnimationFrame；用定时器兜底，
  // 只在异步路径尚未发布状态时执行，避免模板无故报“did not publish status”。
  setTimeout(() => {
    if (!document.documentElement.hasAttribute('data-layout-status')) {
      runLayoutPreflight();
    }
  }, 500);
})();
</script>
"""


def page(inner: str) -> str:
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>'
        + CARD_CSS
        + '</style></head><body style="background:#FAF8F3">'
        + inner
        + LAYOUT_PREFLIGHT_JS
        + "</body></html>"
    )


def card_name(ctx: dict[str, str], slug: str) -> str:
    return f"{ctx['ep']}_{slug}"


def topbar(ctx: dict[str, str], n: str) -> str:
    return (
        '<div class="top"><span class="series">'
        + escape(SERIES)
        + " · 第"
        + escape(ctx["ep"])
        + "集</span><span>"
        + escape(n)
        + " / "
        + TOTAL_TOKEN
        + '</span></div><div class="hr"></div>'
    )


def diagram_card(
    ctx: dict[str, str],
    n: str,
    title: str,
    cap: str,
    viewbox: str,
    scene_js: str,
    below: str = "",
    foot: str | None = None,
    strict: bool = True,
) -> str:
    """图解卡：scene_js 必须画机制，而不是只画标签和方框。"""
    if foot is None:
        foot = f"{SERIES} · {ctx['subject']} · 学习笔记"
    return (
        '<section class="card">'
        + topbar(ctx, n)
        + "<h1>"
        + title
        + "</h1>"
        + ('<p class="cap">' + cap + "</p>" if cap else "")
        + '<div class="diagram"><svg id="s"'
        + (' data-layout-strict="true"' if strict else "")
        + ' viewBox="'
        + escape(viewbox, quote=True)
        + '"></svg></div>'
        + below
        + '<div class="foot">'
        + escape(foot)
        + "</div><script>"
        + scene_js
        + "</script></section>"
    )


def text_card(
    ctx: dict[str, str], n: str, inner: str, foot: str | None = None
) -> str:
    """n 为空时生成封面；普通文字卡会垂直居中。"""
    if not n:
        return '<section class="card cover">' + inner + "</section>"
    if foot is None:
        foot = f"{SERIES} · {ctx['subject']} · 学习笔记"
    return (
        '<section class="card tcard">'
        + topbar(ctx, n)
        + '<div class="fill">'
        + inner
        + '</div><div class="foot">'
        + escape(foot)
        + "</div></section>"
    )


# 通用 SVG scene kit：和模板同文件，复制到新系列后不依赖跨目录 Python 导入。
SCENE_KIT = r"""
const s=document.getElementById('s'),NS='http://www.w3.org/2000/svg';
const __layoutErrors=window.__feynmanLayoutErrors||
  (window.__feynmanLayoutErrors=[]);
let __layoutGuardCounter=0;
function el(t,a,x,parent){
  const e=document.createElementNS(NS,t);
  for(const k in a)e.setAttribute(k,a[k]);
  if(x!=null)e.textContent=x;
  (parent||s).appendChild(e);
  return e;
}
function T(x,y,str,a){
  return el('text',Object.assign({x:x,y:y,
    'font-family':'CoverHeavy, Microsoft YaHei, sans-serif',fill:'#2F3437'},a||{}),str);
}
function layoutError(message,node){
  const text=String(message);
  if(!__layoutErrors.includes(text))__layoutErrors.push(text);
  if(node)node.setAttribute('data-layout-error',text);
  return node;
}
function layoutGuardNodes(node){
  if(!node)return [];
  const roots=(Array.isArray(node)||node instanceof NodeList)?
    Array.from(node):[node];
  const selector='text,line,path,polyline,polygon';
  const result=[];
  roots.forEach((root)=>{
    if(!root||root.nodeType!==1)return;
    if(root.matches&&root.matches(selector))result.push(root);
    if(root.querySelectorAll)result.push(...root.querySelectorAll(selector));
  });
  return Array.from(new Set(result));
}
// Guard 把会参与碰撞检查的文字/连接线登记到同一组。
// role 只能是 text / connector；默认安全距离 16px，结论可传 24。
function Guard(node,role,group,clearance){
  const allowed=role==='text'||role==='connector';
  const name=String(group||'').trim();
  const gap=layoutNumber(clearance,16);
  if(!allowed)layoutError(`GUARD_INVALID_ROLE role=${String(role)}`,node);
  if(!name)layoutError('GUARD_GROUP_MISSING',node);
  if(!(gap>=0))layoutError(`GUARD_INVALID_CLEARANCE value=${String(clearance)}`,node);
  layoutGuardNodes(node).forEach((item)=>{
    item.setAttribute('data-layout-role',role);
    item.setAttribute('data-layout-group',name);
    item.setAttribute('data-layout-clearance',Math.max(0,gap||0));
    item.removeAttribute('data-layout-decoration');
  });
  return node;
}
// Decor 明确声明节点只用于装饰；strict 模式不会把它当语义文字/连接线。
function Decor(node){
  layoutGuardNodes(node).forEach((item)=>{
    item.setAttribute('data-layout-decoration','true');
    item.removeAttribute('data-layout-role');
    item.removeAttribute('data-layout-group');
    item.removeAttribute('data-layout-clearance');
  });
  return node;
}
// 新卡默认 strict；也可对自建 SVG 显式调用 Strict(svg)。
function Strict(node){
  (node||s).setAttribute('data-layout-strict','true');
  return node||s;
}
function guardedControlledText(node,options){
  const o=options||{};
  const group=String(o.guardGroup||
    `controlled-${++__layoutGuardCounter}`);
  return Guard(node,'text',group,layoutNumber(o.clearance,16));
}
function layoutNumber(value,fallback){
  const parsed=Number.parseFloat(value);
  return Number.isFinite(parsed)?parsed:fallback;
}
function layoutOptions(options,fallbackWidth){
  const o=options||{};
  const maxWidth=layoutNumber(o.maxWidth,fallbackWidth);
  const padding=layoutNumber(o.padding,24);
  const minFontSize=layoutNumber(o.minFontSize,16);
  if(!(maxWidth>0))layoutError('maxWidth must be positive');
  if(!(padding>=0))layoutError('padding must be non-negative');
  if(!(minFontSize>0))layoutError('minFontSize must be positive');
  return Object.assign({},o,{
    maxWidth:Math.max(1,maxWidth||1),
    padding:Math.max(0,padding||0),
    minFontSize:Math.max(1,minFontSize||1)
  });
}
function layoutAnchor(align){
  if(align==='center'||align==='middle')return 'middle';
  if(align==='right'||align==='end')return 'end';
  return 'start';
}
function layoutTextX(x,innerWidth,padding,anchor){
  if(anchor==='middle')return x+padding+innerWidth/2;
  if(anchor==='end')return x+padding+innerWidth;
  return x+padding;
}
function registerTextBounds(node,left,top,right,bottom,minFontSize,padding,kind){
  node.setAttribute('data-layout-controlled',kind||'text');
  node.setAttribute('data-layout-left',left);
  if(Number.isFinite(top))node.setAttribute('data-layout-top',top);
  node.setAttribute('data-layout-right',right);
  if(Number.isFinite(bottom))node.setAttribute('data-layout-bottom',bottom);
  node.setAttribute('data-layout-min-font-size',minFontSize);
  node.setAttribute('data-layout-padding',padding);
  return node;
}
function measureText(node,value){
  node.textContent=value;
  return node.getComputedTextLength();
}
// x 是可用框左边，y 是基线。字号只会降到 minFontSize；再放不下就报错。
function TFit(x,y,str,a,options){
  const o=layoutOptions(options,0);
  const attrs=Object.assign({},a||{});
  const startSize=layoutNumber(attrs['font-size'],24);
  const innerWidth=Math.max(1,o.maxWidth-o.padding*2);
  const anchor=layoutAnchor(o.align||attrs['text-anchor']);
  attrs['text-anchor']=anchor;
  attrs['font-size']=Math.max(startSize,o.minFontSize);
  const node=T(layoutTextX(x,innerWidth,o.padding,anchor),y,str,attrs);
  let size=layoutNumber(attrs['font-size'],24);
  while(measureText(node,str)>innerWidth&&size>o.minFontSize){
    size=Math.max(o.minFontSize,size-1);
    node.setAttribute('font-size',size);
  }
  if(node.getComputedTextLength()>innerWidth+0.5){
    layoutError(
      `TFit overflow at minimum ${o.minFontSize}px: ${String(str).slice(0,48)}`,
      node
    );
  }
  registerTextBounds(
    node,x+o.padding,NaN,x+o.maxWidth-o.padding,NaN,
    o.minFontSize,o.padding,'fit'
  );
  return guardedControlledText(node,o);
}
function layoutTokens(value){
  const text=String(value);
  if(!text)return [''];
  if(window.Intl&&Intl.Segmenter){
    const segmenter=new Intl.Segmenter('zh-CN',{granularity:'word'});
    return Array.from(segmenter.segment(text),part=>part.segment);
  }
  return Array.from(text);
}
function wrapParagraph(node,value,width){
  const tokens=layoutTokens(value);
  const lines=[];
  let line='';
  for(const token of tokens){
    const candidate=line+token;
    if(!line||measureText(node,candidate)<=width){
      line=candidate;
      continue;
    }
    lines.push(line.trimEnd());
    line=token.trimStart();
    if(measureText(node,line)>width){
      let fragment='';
      for(const char of Array.from(line)){
        if(fragment&&measureText(node,fragment+char)>width){
          lines.push(fragment);
          fragment=char;
        }else{
          fragment+=char;
        }
      }
      line=fragment;
    }
  }
  lines.push(line.trimEnd());
  return lines;
}
function wrappedLines(node,value,width){
  const lines=[];
  String(value).split('\n').forEach((paragraph)=>{
    lines.push(...wrapParagraph(node,paragraph,width));
  });
  return lines;
}
// x/y 是文字可用框左上角；maxHeight/maxLines 可选。
function TWrap(x,y,str,a,options){
  const o=layoutOptions(options,0);
  const attrs=Object.assign({},a||{});
  const startSize=layoutNumber(attrs['font-size'],24);
  const innerWidth=Math.max(1,o.maxWidth-o.padding*2);
  const maxHeight=layoutNumber(o.maxHeight,Infinity);
  const maxLines=layoutNumber(o.maxLines,Infinity);
  const anchor=layoutAnchor(o.align||attrs['text-anchor']);
  attrs['text-anchor']=anchor;
  attrs['font-size']=Math.max(startSize,o.minFontSize);
  const node=T(0,0,'',attrs);
  let size=layoutNumber(attrs['font-size'],24);
  let lines=[];
  let lineHeight=0;
  let fits=false;
  while(size>=o.minFontSize){
    node.setAttribute('font-size',size);
    lines=wrappedLines(node,str,innerWidth);
    lineHeight=layoutNumber(o.lineHeight,size*1.45);
    const needed=lines.length*lineHeight;
    if(lines.length<=maxLines&&needed<=Math.max(1,maxHeight-o.padding*2)){
      fits=true;
      break;
    }
    if(size===o.minFontSize)break;
    size=Math.max(o.minFontSize,size-1);
  }
  if(!fits){
    layoutError(
      `TWrap overflow at minimum ${o.minFontSize}px: ${String(str).slice(0,48)}`,
      node
    );
  }
  node.textContent='';
  const textX=layoutTextX(x,innerWidth,o.padding,anchor);
  lines.forEach((line,index)=>{
    el('tspan',{
      x:textX,
      y:y+o.padding+size+index*lineHeight
    },line,node);
  });
  registerTextBounds(
    node,x+o.padding,y+o.padding,x+o.maxWidth-o.padding,
    Number.isFinite(maxHeight)?y+maxHeight-o.padding:NaN,
    o.minFontSize,o.padding,'wrap'
  );
  return guardedControlledText(node,o);
}
// BoxText 画框并排字；默认 24px 内边距，显式更小会让预检失败。
function BoxText(x,y,w,h,str,a,options){
  const raw=options||{};
  const requestedWidth=layoutNumber(raw.maxWidth,w);
  const maxWidth=Math.min(w,requestedWidth);
  const maxHeight=Math.min(h,layoutNumber(raw.maxHeight,h));
  const o=layoutOptions(
    Object.assign({},raw,{maxWidth:maxWidth,maxHeight:maxHeight}),w
  );
  const group=el('g',{'data-layout-box':'true'});
  const frame=R(
    x,y,w,h,layoutNumber(raw.radius,16),
    raw.fill||'#FAF8F3',raw.stroke||'#7E8B6D',
    layoutNumber(raw.strokeWidth,2)
  );
  group.appendChild(frame);
  const offsetX=(w-maxWidth)/2;
  const text=TWrap(x+offsetX,y,str,a,Object.assign({},o,{maxWidth:maxWidth}));
  text.setAttribute('data-layout-controlled','box-text');
  group.appendChild(text);
  if(requestedWidth>w){
    layoutError(`BoxText maxWidth ${requestedWidth} exceeds box width ${w}`,text);
  }
  if(o.padding<24){
    layoutError(`BoxText padding ${o.padding} is below 24 logical px`,text);
  }
  return group;
}
function R(x,y,w,h,r,fill,stroke,sw){
  return el('rect',{x:x,y:y,width:w,height:h,rx:r,fill:fill||'#fff',
    stroke:stroke||'#e7e1d6','stroke-width':sw||2});
}
function L(x1,y1,x2,y2,color,width,dash){
  const a={x1:x1,y1:y1,x2:x2,y2:y2,stroke:color||'#7E8B6D',
    'stroke-width':width||3,'stroke-linecap':'round'};
  if(dash)a['stroke-dasharray']=dash;
  return el('line',a);
}
function C(x,y,r,fill,stroke,sw){
  return el('circle',{cx:x,cy:y,r:r,fill:fill||'#fff',
    stroke:stroke||'#7E8B6D','stroke-width':sw||2});
}
function P(points,fill,stroke,sw){
  return el('polygon',{points:points,fill:fill||'#7E8B6D',
    stroke:stroke||'none','stroke-width':sw||0,'stroke-linejoin':'round'});
}
function Path(d,color,width,dash,fill){
  const a={d:d,fill:fill||'none',stroke:color||'#7E8B6D',
    'stroke-width':width||3,'stroke-linecap':'round','stroke-linejoin':'round'};
  if(dash)a['stroke-dasharray']=dash;
  return el('path',a);
}
function right(x1,y,x2,color){
  const group=el('g',{'data-layout-bundle':'connector'});
  group.appendChild(L(x1,y,x2-14,y,color||'#7E8B6D',4));
  group.appendChild(
    P(`${x2-18},${y-9} ${x2-18},${y+9} ${x2},${y}`,
      color||'#7E8B6D')
  );
  return group;
}
function down(x,y1,y2,color){
  const group=el('g',{'data-layout-bundle':'connector'});
  group.appendChild(L(x,y1,x,y2-14,color||'#7E8B6D',4));
  group.appendChild(
    P(`${x-9},${y2-18} ${x+9},${y2-18} ${x},${y2}`,
      color||'#7E8B6D')
  );
  return group;
}
function grid(x,y,w,h,step,color){
  const ink=color||'#dfe4d9';
  for(let gx=x;gx<=x+w;gx+=step)Decor(L(gx,y,gx,y+h,ink,1));
  for(let gy=y;gy<=y+h;gy+=step)Decor(L(x,gy,x+w,gy,ink,1));
}
function bolt(x,y,r){
  C(x,y,r,'#FAF8F3','#5f6b50',2);
  Decor(L(x-r*.55,y,x+r*.55,y,'#5f6b50',2));
  Decor(L(x,y-r*.55,x,y+r*.55,'#5f6b50',2));
}
function dial(cx,cy,r,angle,color){
  Decor(Path(
    `M ${cx-r*.78} ${cy+r*.18} A ${r*.82} ${r*.82} 0 0 1 ${cx+r*.78} ${cy+r*.18}`,
    '#c7c2b7',3
  ));
  for(let a=-145;a<=-35;a+=22){
    const q=a*Math.PI/180;
    Decor(L(cx+Math.cos(q)*r*.68,cy+Math.sin(q)*r*.68,
      cx+Math.cos(q)*r*.84,cy+Math.sin(q)*r*.84,'#9f9a90',2));
  }
  const q=angle*Math.PI/180;
  Decor(L(cx,cy,cx+Math.cos(q)*r*.68,cy+Math.sin(q)*r*.68,
    color||'#b06a5a',4));
  C(cx,cy,5,color||'#b06a5a',color||'#b06a5a',1);
}
function lockIcon(x,y,scale){
  const z=scale||1;
  Decor(Path(`M ${x+7*z} ${y+18*z} v ${-6*z}
    a ${11*z} ${11*z} 0 0 1 ${22*z} 0 v ${6*z}`,'#5f6b50',3));
  R(x,y+18*z,36*z,29*z,6*z,'#e7ecdf','#5f6b50',3);
  C(x+18*z,y+31*z,3.5*z,'#5f6b50','#5f6b50',1);
  Decor(L(x+18*z,y+34*z,x+18*z,y+41*z,'#5f6b50',2));
}
function ghostTrail(points,options){
  const o=options||{};
  const group=el('g',{'data-layout-bundle':'trail'});
  if(o.path)group.appendChild(
    Path(o.path,o.pathColor||'#7E8B6D',o.pathWidth||3,o.pathDash||'8 8')
  );
  points.forEach((p,i)=>{
    const x=Array.isArray(p)?p[0]:p.x;
    const y=Array.isArray(p)?p[1]:p.y;
    const opacity=(Array.isArray(p)?p[2]:p.opacity);
    const dot=C(x,y,o.r||13,o.fill||'#b06a5a',o.stroke||'#FAF8F3',o.sw||3);
    dot.setAttribute('opacity',opacity==null?(i+1)/points.length:opacity);
    group.appendChild(dot);
  });
  return group;
}
function stageStamp(x,y,label,color){
  const ink=color||'#b06a5a';
  R(x,y,126,42,21,'none',ink,3);
  Decor(T(x+63,y+29,label,{'text-anchor':'middle','font-size':17,
    'font-weight':800,fill:ink,'letter-spacing':1}));
}
function teachingBadge(x,y){
  R(x,y,116,38,19,'#FAF8F3','#b06a5a',2);
  Decor(T(x+58,y+26,'教学示意',{'text-anchor':'middle','font-size':16,
    'font-weight':700,fill:'#9b5649'}));
}
"""


# 静态关键帧示例：展示“对象沿路径变化”，不是默认知识内容或默认皮肤。
STARTER_MECHANISM_SCENE = SCENE_KIT + r"""
R(34,82,692,770,22,'#f7f5ef','#d7d1c7',2);
grid(56,104,648,726,54);
bolt(50,98,6); bolt(710,98,6); bolt(50,836,6); bolt(710,836,6);

stageStamp(58,34,'BEFORE','#9b5649');
stageStamp(317,34,'CHANGE','#5f6b50');
stageStamp(576,34,'AFTER','#5f6b50');

Guard(Path('M 118 650 C 224 560, 244 300, 382 382 S 584 690, 654 266',
  '#7E8B6D',5,'10 10'),'connector','object-flow',16);
Guard(ghostTrail([[118,650,.22],[208,542,.35],[278,386,.5],[382,382,.66],
  [494,552,.82],[594,500,.92],[654,266,1]],{r:17,fill:'#b06a5a'}),
  'connector','object-flow',16);
Guard(P('642,279 669,249 666,290','#5f6b50'),
  'connector','object-flow',16);

C(118,650,54,'#f2e2dc','#b06a5a',4);
Guard(T(118,660,'0.20',{'text-anchor':'middle',
  'font-family':'Consolas, monospace','font-size':23,'font-weight':800,
  fill:'#9b5649'}),'text','start-value',16);
C(654,266,60,'#e7ecdf','#5f6b50',4);
Guard(T(654,276,'0.80',{'text-anchor':'middle',
  'font-family':'Consolas, monospace','font-size':23,'font-weight':800,
  fill:'#5f6b50'}),'text','end-value',16);

R(268,678,224,126,16,'#FAF8F3','#7E8B6D',3);
Guard(T(380,716,'参数前后状态',{'text-anchor':'middle','font-size':20,
  'font-weight':800,fill:'#5f6b50'}),'text','dial-label',16);
dial(333,770,38,-132,'#b06a5a');
Guard(right(375,770,414,'#7E8B6D'),'connector','dial-arrow',16);
dial(452,770,38,-46,'#5f6b50');
lockIcon(632,686,1.25);

Guard(T(118,744,'对象起点',{'text-anchor':'middle','font-size':21,
  'font-weight':800,fill:'#9b5649'}),'text','start-label',16);
Guard(T(654,358,'对象终态',{'text-anchor':'middle','font-size':21,
  'font-weight':800,fill:'#5f6b50'}),'text','end-label',16);
Guard(T(380,908,'关键帧 + 轨迹残影 + 数值前后状态',
  {'text-anchor':'middle','font-size':29,'font-weight':900}),
  'text','conclusion',24);
Guard(T(380,970,'把这些占位对象换成本节真实机制',
  {'text-anchor':'middle','font-size':22,fill:'#6b6b6b'}),
  'text','conclusion',24);
teachingBadge(610,1006);
Strict();
"""


def build_starter_episode(ctx: dict[str, str]) -> list[tuple[str, str]]:
    """第一集起步样例；复制 builder 并注册即可增加 episode。"""
    return [
        (
            card_name(ctx, "01_cover"),
            page(
                text_card(
                    ctx,
                    "",
                    '<div class="ctitle"><div class="ln smallline">材料原名</div>'
                    '<div class="ln">本节问题</div>'
                    '<div class="ln last">关键词</div></div>'
                    '<div class="csub">作者 · 头衔 · 机构<br>'
                    f"费曼精读存档 · 第 {escape(ctx['ep'])} 集 · YYYY-MM-DD</div>",
                )
            ),
        ),
        (
            card_name(ctx, "02_mechanism"),
            page(
                diagram_card(
                    ctx,
                    "02",
                    "机制图示例：让变化留在画面里",
                    "示例同时展示<b>轨迹残影、数值前后状态与阶段戳</b>。"
                    "正式成册时，换成本节 visual brief 中的真实对象和因果。",
                    "0 0 760 1080",
                    STARTER_MECHANISM_SCENE,
                )
            ),
        ),
        (
            card_name(ctx, "03_summary"),
            page(
                text_card(
                    ctx,
                    "03",
                    "<h1>小结 / 卡点</h1>"
                    '<div class="note">一句话收拢本节机制：谁在什么阶段，'
                    "发生了什么可见变化。</div>"
                    '<div class="item"><b>机制证据</b>'
                    '<span class="d">对象创建 / 数值改变 / 信息流 / 因果接力。</span></div>'
                    '<div class="item"><b>正确边界</b>'
                    '<span class="d">复习成品只写核实后的正确机制与边界；错误原话只进视觉导演单生产记录。</span></div>'
                    '<p class="small">下一入口：只记录，不自动开始下一节。</p>',
                )
            ),
        ),
    ]


# 例:
# def build_episode_02(ctx):
#     return [...]
#
# EPISODES["02"] = {"subject": "第二节主题", "builder": build_episode_02}
EpisodeBuilder = Callable[[dict[str, str]], list[tuple[str, str]]]
EPISODES: dict[str, dict[str, str | EpisodeBuilder]] = {
    "01": {"subject": "起步示例", "builder": build_starter_episode},
}


def validate_episode_id(ep: str) -> None:
    """episode 必须是两位数字，避免文件前缀和清理 glob 越界。"""
    if len(ep) != 2 or not ep.isascii() or not ep.isdigit():
        raise ValueError(f"episode 必须是两位数字（如 01）: {ep!r}")


def build_cards(ep: str) -> tuple[str, list[tuple[str, str]]]:
    validate_episode_id(ep)
    spec = EPISODES[ep]
    subject = str(spec["subject"])
    builder = spec["builder"]
    if not callable(builder):
        raise TypeError(f"episode {ep} 的 builder 不可调用")
    ctx = {"ep": ep, "subject": subject}
    raw_cards = builder(ctx)
    if not raw_cards:
        raise ValueError(f"episode {ep} 没有卡片")

    total = f"{len(raw_cards):02d}"
    seen: set[str] = set()
    cards: list[tuple[str, str]] = []
    for name, html in raw_cards:
        if name in seen:
            raise ValueError(f"episode {ep} 有重复卡名: {name}")
        if not name.startswith(ep + "_"):
            raise ValueError(f"卡名必须以 {ep}_ 开头: {name}")
        if "/" in name or "\\" in name:
            raise ValueError(f"卡名不能包含路径分隔符: {name}")
        seen.add(name)
        cards.append((name, html.replace(TOTAL_TOKEN, total)))
    return subject, cards


def wait_for_file(path: Path, timeout: float = 12.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.is_file() and path.stat().st_size > 0:
            return True
        time.sleep(0.2)
    return False


def run_layout_preflight(html_path: Path, user_data: Path) -> tuple[bool, str]:
    """用 Chromium 执行 DOM/SVG/受控文字预检；失败时不进入截图。"""
    command = [
        str(BROWSER),
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        "--allow-file-access-from-files",
        "--user-data-dir=" + str(user_data),
        "--hide-scrollbars",
        "--virtual-time-budget=4000",
        "--window-size=1080,1440",
        "--dump-dom",
        html_path.as_uri(),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=35,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "layout preflight timed out"
    if result.returncode != 0:
        detail = result.stderr.strip()[-1200:]
        return False, f"layout preflight Chromium exit {result.returncode}: {detail}"

    status_match = re.search(
        r'<html\b[^>]*\bdata-layout-status="([^"]+)"',
        result.stdout,
        flags=re.IGNORECASE,
    )
    report_match = re.search(
        r'<pre\b[^>]*\bid="layout-preflight-report"[^>]*>(.*?)</pre>',
        result.stdout,
        flags=re.IGNORECASE | re.DOTALL,
    )
    detail = ""
    if report_match:
        detail = unescape(re.sub(r"<[^>]+>", "", report_match.group(1))).strip()
    if not status_match:
        return False, detail or "layout preflight did not publish a status"
    status = status_match.group(1).lower()
    if status != "ok":
        return False, detail or f"layout preflight status={status}"
    return True, "layout preflight: 0 errors"


def png_dimensions(path: Path) -> tuple[int, int] | None:
    """验证 PNG chunk/CRC、完整 zlib 像素流与 scanline，再返回尺寸。"""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 45 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None

    position = 8
    dimensions: tuple[int, int] | None = None
    png_format: tuple[int, int, int, int, int, int, int] | None = None
    idat_parts: list[bytes] = []
    idat_closed = False
    while position + 12 <= len(data):
        length = struct.unpack(">I", data[position : position + 4])[0]
        kind = data[position + 4 : position + 8]
        payload_start = position + 8
        payload_end = payload_start + length
        chunk_end = payload_end + 4
        if chunk_end > len(data):
            return None
        payload = data[payload_start:payload_end]
        stored_crc = struct.unpack(">I", data[payload_end:chunk_end])[0]
        actual_crc = binascii.crc32(kind + payload) & 0xFFFFFFFF
        if stored_crc != actual_crc:
            return None
        if kind == b"IHDR":
            if position != 8 or length != 13 or dimensions is not None:
                return None
            png_format = struct.unpack(">IIBBBBB", payload)
            dimensions = png_format[:2]
        elif kind == b"IDAT":
            if dimensions is None or idat_closed:
                return None
            idat_parts.append(payload)
        elif kind == b"IEND":
            if length != 0 or chunk_end != len(data):
                return None
            if png_format is None or not idat_parts:
                return None
            width, height, bit_depth, color_type, compression, filter_method, interlace = png_format
            channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
            allowed_depths = {
                0: {1, 2, 4, 8, 16},
                2: {8, 16},
                3: {1, 2, 4, 8},
                4: {8, 16},
                6: {8, 16},
            }
            if (
                width == 0
                or height == 0
                or channels is None
                or bit_depth not in allowed_depths[color_type]
                or compression != 0
                or filter_method != 0
                or interlace != 0
            ):
                return None
            row_bytes = (width * channels * bit_depth + 7) // 8
            expected = height * (row_bytes + 1)
            if expected <= 0 or expected > 128 * 1024 * 1024:
                return None
            try:
                decoder = zlib.decompressobj()
                pixels = decoder.decompress(b"".join(idat_parts), expected + 1)
            except zlib.error:
                return None
            if (
                len(pixels) != expected
                or not decoder.eof
                or decoder.unused_data
                or decoder.unconsumed_tail
            ):
                return None
            stride = row_bytes + 1
            if any(pixels[offset] > 4 for offset in range(0, expected, stride)):
                return None
            return dimensions
        elif idat_parts:
            idat_closed = True
        position = chunk_end
    return None


def guard_probe_output(cards_dir: Path, png_dir: Path) -> None:
    """探针模式只允许写系统临时目录，防止测试误用正式卡组路径。"""
    raw_root = os.environ.get("FEYNMAN_RENDER_PROBE_ROOT")
    if not raw_root:
        return
    temp_root = Path(tempfile.gettempdir()).resolve()
    probe_root = Path(raw_root).resolve()
    if probe_root != temp_root and temp_root not in probe_root.parents:
        raise RuntimeError(f"probe root must be inside system temp: {probe_root}")
    for target in (cards_dir.resolve(), png_dir.resolve()):
        if target != probe_root and probe_root not in target.parents:
            raise RuntimeError(
                f"probe output escaped temp root: {target} not under {probe_root}"
            )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def card_set_sha256(card_records: list[dict]) -> str:
    ordered_identity = [
        {"order": record["order"], "sha256": record["sha256"]}
        for record in card_records
    ]
    return canonical_sha256(ordered_identity)


def series_slug() -> str:
    explicit = os.environ.get("FEYNMAN_NOTES_SERIES_SLUG", "").strip()
    if explicit:
        return explicit
    if SCRIPT_DIR.name.lower() == "cards":
        return SCRIPT_DIR.parent.name
    slug = re.sub(r"[^a-z0-9]+", "-", SERIES.lower()).strip("-")
    return slug or "unknown-series"


def workspace_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(WORKSPACE_ROOT.resolve()).as_posix()
    except ValueError:
        # Installed skill paths can live outside the user's learning workspace.
        # Manifest provenance should not publish machine-specific absolute paths.
        try:
            return "skill:feynman-notes/" + path.resolve().relative_to(SKILL_DIR).as_posix()
        except ValueError:
            return path.name


def resolve_visual_metadata(ep: str, subject: str) -> tuple[dict, dict]:
    """The public edition has one built-in visual baseline and no policy registry."""
    del subject
    brief_path = SCRIPT_DIR / f"{ep}-visual-brief.md"
    visual = {
        "strategy_id": "visual-v0",
        "version": "v0",
        "status": "builtin",
        "source_path": "builtin:feynman-notes/visual-v0",
        "source_sha256": None,
        "series_skeleton_id": f"{series_slug()}-series-v0",
        "theme_skin_id": "series-baseline",
        "scope": "full-card-set",
        "resolved_variables": VISUAL_BASELINE_V0,
    }
    brief = {
        "visual_brief": workspace_relative(brief_path) if brief_path.is_file() else None,
    }
    return visual, brief


def infer_card_role(name: str, order: int, total: int) -> str:
    suffix = name.lower()
    if "cover" in suffix or order == 1:
        return "cover"
    if any(token in suffix for token in ("summary", "recap", "conclusion")):
        return "summary"
    if order == total and any(token in suffix for token in ("next", "question", "checkpoint")):
        return "next-entry"
    return "mechanism"


def build_manifest_document(
    ep: str,
    subject: str,
    cards: list[tuple[str, str]],
    stage_png: Path,
    stage_gallery: Path,
    provenance_status: str,
) -> dict:
    visual, brief = resolve_visual_metadata(ep, subject)
    card_records = []
    for order, (name, _html) in enumerate(cards, start=1):
        path = stage_png / f"{name}.png"
        dimensions = png_dimensions(path)
        if dimensions is None:
            raise RuntimeError(f"manifest cannot decode PNG: {path}")
        width, height = dimensions
        card_records.append(
            {
                "order": order,
                "role": infer_card_role(name, order, len(cards)),
                "file": f"png/{name}.png",
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "width": width,
                "height": height,
            }
        )
    gallery_record = {
        "file": stage_gallery.name,
        "sha256": sha256_file(stage_gallery),
        "bytes": stage_gallery.stat().st_size,
    }
    identity = {
        "series_slug": series_slug(),
        "episode_id": ep,
        "subject": subject,
        "visual": visual,
        "cards": card_records,
        "gallery": gallery_record,
    }
    return {
        "schema_version": MANIFEST_SCHEMA,
        "artifact_kind": MANIFEST_ARTIFACT_KIND,
        **identity,
        "provenance": provenance_status,
        "provenance_detail": {
            "renderer": workspace_relative(SCRIPT_PATH),
            "visual_brief": brief["visual_brief"],
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        },
        "card_set_sha256": card_set_sha256(card_records),
        "manifest_identity_sha256": canonical_sha256(identity),
    }


def write_manifest(
    ep: str,
    subject: str,
    cards: list[tuple[str, str]],
    stage_png: Path,
    stage_gallery: Path,
    stage_manifest: Path,
    provenance_status: str,
) -> Path:
    document = build_manifest_document(
        ep,
        subject,
        cards,
        stage_png,
        stage_gallery,
        provenance_status,
    )
    stage_manifest.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return stage_manifest


def validate_manifest_schema(document: dict) -> None:
    schema_path = CARD_MANIFEST_SCHEMA_PATH
    if not schema_path.is_file():
        raise RuntimeError(f"card manifest schema missing: {schema_path}")
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid card manifest schema: {exc}") from exc
    try:
        import jsonschema
    except ImportError as exc:
        raise RuntimeError(
            "jsonschema is required to validate card manifests"
        ) from exc
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(document)
    except (
        jsonschema.exceptions.SchemaError,
        jsonschema.exceptions.ValidationError,
    ) as exc:
        raise RuntimeError(f"card manifest JSON Schema validation failed: {exc.message}") from exc


def validate_manifest(
    ep: str,
    subject: str,
    cards: list[tuple[str, str]],
    stage_png: Path,
    stage_gallery: Path,
    stage_manifest: Path,
) -> None:
    try:
        document = json.loads(stage_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid staged manifest: {exc}") from exc
    validate_manifest_schema(document)
    if document.get("schema_version") != MANIFEST_SCHEMA:
        raise RuntimeError("manifest schema mismatch")
    if document.get("artifact_kind") != MANIFEST_ARTIFACT_KIND:
        raise RuntimeError("manifest artifact_kind mismatch")
    if document.get("series_slug") != series_slug():
        raise RuntimeError("manifest series mismatch")
    if document.get("episode_id") != ep or document.get("subject") != subject:
        raise RuntimeError("manifest episode identity mismatch")
    if document.get("provenance") not in {"rendered", "reconstructed"}:
        raise RuntimeError("manifest provenance mismatch")
    expected_visual, _brief = resolve_visual_metadata(ep, subject)
    if document.get("visual") != expected_visual:
        raise RuntimeError("manifest visual metadata mismatch")

    expected_cards = []
    for order, (name, _html) in enumerate(cards, start=1):
        path = stage_png / f"{name}.png"
        width, height = png_dimensions(path) or (0, 0)
        expected_cards.append(
            {
                "order": order,
                "role": infer_card_role(name, order, len(cards)),
                "file": f"png/{name}.png",
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "width": width,
                "height": height,
            }
        )
    if document.get("cards") != expected_cards:
        raise RuntimeError("manifest card order or file metadata mismatch")
    expected_gallery = {
        "file": stage_gallery.name,
        "sha256": sha256_file(stage_gallery),
        "bytes": stage_gallery.stat().st_size,
    }
    if document.get("gallery") != expected_gallery:
        raise RuntimeError("manifest gallery hash mismatch")
    identity = {
        "series_slug": document["series_slug"],
        "episode_id": document["episode_id"],
        "subject": document["subject"],
        "visual": document["visual"],
        "cards": document["cards"],
        "gallery": document["gallery"],
    }
    if document.get("card_set_sha256") != card_set_sha256(document["cards"]):
        raise RuntimeError("manifest card_set_sha256 mismatch")
    if document.get("manifest_identity_sha256") != canonical_sha256(identity):
        raise RuntimeError("manifest manifest_identity_sha256 mismatch")


def write_gallery(
    ep: str,
    subject: str,
    cards: list[tuple[str, str]],
    gallery: Path,
) -> Path:
    figures = "".join(
        '<figure><img src="png/'
        + escape(name, quote=True)
        + '.png" alt="'
        + escape(name, quote=True)
        + '"><figcaption>'
        + escape(name)
        + "</figcaption></figure>"
        for name, _ in cards
    )
    gallery.write_text(
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>'
        "body{margin:0;background:#E5E0D6;display:flex;flex-direction:column;"
        'align-items:center;gap:36px;padding:44px;font-family:"Noto Sans SC",'
        '"Microsoft YaHei",sans-serif}figure{margin:0;text-align:center}'
        "img{width:540px;height:auto;box-shadow:0 8px 28px rgba(0,0,0,.14);"
        "border-radius:6px;display:block}figcaption{font-size:13px;color:#8a857c;"
        "margin-top:8px}</style></head><body>"
        '<h2 style="color:#5f6b50">'
        + escape(SERIES)
        + " · 第 "
        + escape(ep)
        + " 集（"
        + escape(subject)
        + " 知识卡）</h2>"
        + figures
        + "</body></html>",
        encoding="utf-8",
    )
    return gallery


def validate_staged_episode(
    ep: str,
    subject: str,
    cards: list[tuple[str, str]],
    stage_png: Path,
    stage_gallery: Path,
    stage_manifest: Path,
) -> None:
    """提交前验证 staging 的 PNG、贴图页、manifest 与顺序。"""
    expected_files = sorted(f"{name}.png" for name, _ in cards)
    actual_files = sorted(path.name for path in stage_png.glob(f"{ep}_*.png"))
    if actual_files != expected_files:
        raise RuntimeError(
            f"staging PNG mismatch: expected {expected_files}, got {actual_files}"
        )
    for filename in expected_files:
        path = stage_png / filename
        if png_dimensions(path) != (2160, 2880):
            raise RuntimeError(f"invalid PNG dimensions: {path}")

    if not stage_gallery.is_file():
        raise RuntimeError(f"staging gallery missing: {stage_gallery}")
    body = stage_gallery.read_text(encoding="utf-8")
    links = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', body)
    expected_links = [f"png/{name}.png" for name, _ in cards]
    if links != expected_links:
        raise RuntimeError(
            f"staging gallery links mismatch: expected {expected_links}, got {links}"
        )
    for link in links:
        if not (stage_gallery.parent / Path(link)).is_file():
            raise RuntimeError(f"staging gallery target missing: {link}")
    validate_manifest(
        ep,
        subject,
        cards,
        stage_png,
        stage_gallery,
        stage_manifest,
    )


def commit_staged_episode(
    ep: str,
    cards_dir: Path,
    png_dir: Path,
    stage_png: Path,
    stage_gallery: Path,
    stage_manifest: Path,
) -> None:
    """事务式替换单集产物；失败时恢复旧 PNG、HTML 与 manifest。"""
    backup_dir = Path(
        tempfile.mkdtemp(prefix=f".render-backup-{ep}-", dir=cards_dir)
    )
    backup_png = backup_dir / "png"
    backup_png.mkdir(parents=True, exist_ok=True)
    formal_gallery = cards_dir / f"{ep}-cards.html"
    formal_manifest = cards_dir / f"{ep}-card-manifest.json"
    backup_pairs: list[tuple[Path, Path]] = []
    installed: list[Path] = []

    try:
        for old in sorted(png_dir.glob(f"{ep}_*.png")):
            backup = backup_png / old.name
            os.replace(old, backup)
            backup_pairs.append((old, backup))
        if formal_gallery.exists():
            backup = backup_dir / formal_gallery.name
            os.replace(formal_gallery, backup)
            backup_pairs.append((formal_gallery, backup))
        if formal_manifest.exists():
            backup = backup_dir / formal_manifest.name
            os.replace(formal_manifest, backup)
            backup_pairs.append((formal_manifest, backup))

        for staged in sorted(stage_png.glob(f"{ep}_*.png")):
            formal = png_dir / staged.name
            os.replace(staged, formal)
            installed.append(formal)
        os.replace(stage_gallery, formal_gallery)
        installed.append(formal_gallery)
        os.replace(stage_manifest, formal_manifest)
        installed.append(formal_manifest)
    except BaseException as exc:
        rollback_errors: list[str] = []
        for path in reversed(installed):
            try:
                if path.exists():
                    path.unlink()
            except OSError as rollback_exc:
                rollback_errors.append(f"remove {path}: {rollback_exc}")
        for formal, backup in reversed(backup_pairs):
            try:
                if backup.exists():
                    os.replace(backup, formal)
            except OSError as rollback_exc:
                rollback_errors.append(f"restore {formal}: {rollback_exc}")
        if rollback_errors:
            raise RuntimeError(
                f"commit failed and rollback was incomplete; backup preserved at "
                f"{backup_dir}: "
                + "; ".join(rollback_errors)
            ) from exc
        shutil.rmtree(backup_dir, ignore_errors=True)
        raise
    else:
        shutil.rmtree(backup_dir, ignore_errors=True)


def commit_staged_manifest(ep: str, cards_dir: Path, stage_manifest: Path) -> None:
    """回填旧卡时只原子替换 manifest，不触碰正式 PNG / HTML。"""
    os.replace(stage_manifest, cards_dir / f"{ep}-card-manifest.json")


def validate_formal_manifest(ep: str) -> bool:
    """只读验收正式 manifest 及其引用的 PNG、HTML 与视觉策略。"""
    subject, cards = build_cards(ep)
    gallery = SCRIPT_DIR / f"{ep}-cards.html"
    manifest = SCRIPT_DIR / f"{ep}-card-manifest.json"
    try:
        validate_staged_episode(
            ep,
            subject,
            cards,
            PNG_DIR,
            gallery,
            manifest,
        )
    except (OSError, RuntimeError) as exc:
        print(f"INVALID MANIFEST {ep}: {exc}", file=sys.stderr)
        return False
    print(f"VALID MANIFEST {ep} {len(cards)}/{len(cards)} PNG")
    return True


def reconstruct_manifest(ep: str) -> bool:
    """从已存在的正式 PNG / HTML 回填 manifest，保持旧文件字节和时间戳。"""
    guard_probe_output(SCRIPT_DIR, PNG_DIR)
    subject, cards = build_cards(ep)
    formal_gallery = SCRIPT_DIR / f"{ep}-cards.html"
    if not formal_gallery.is_file():
        print(f"ERROR gallery missing: {formal_gallery}", file=sys.stderr)
        return False
    stage_root = Path(
        tempfile.mkdtemp(prefix=f".manifest-staging-{ep}-", dir=SCRIPT_DIR)
    )
    stage_png = stage_root / "png"
    stage_png.mkdir()
    stage_gallery = stage_root / formal_gallery.name
    stage_manifest = stage_root / f"{ep}-card-manifest.json"
    try:
        shutil.copy2(formal_gallery, stage_gallery)
        for name, _html in cards:
            source = PNG_DIR / f"{name}.png"
            if not source.is_file():
                raise RuntimeError(f"formal PNG missing: {source}")
            shutil.copy2(source, stage_png / source.name)
        write_manifest(
            ep,
            subject,
            cards,
            stage_png,
            stage_gallery,
            stage_manifest,
            "reconstructed",
        )
        validate_staged_episode(
            ep,
            subject,
            cards,
            stage_png,
            stage_gallery,
            stage_manifest,
        )
        commit_staged_manifest(ep, SCRIPT_DIR, stage_manifest)
        print(f"MANIFEST {ep} reconstructed {len(cards)}/{len(cards)} PNG")
        return True
    except (OSError, RuntimeError) as exc:
        print(
            f"ERROR episode {ep} manifest not committed; old artifacts preserved: {exc}",
            file=sys.stderr,
        )
        return False
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)


def render_episode(ep: str) -> bool:
    guard_probe_output(SCRIPT_DIR, PNG_DIR)
    if not BROWSER.is_file():
        print(f"ERROR Chromium browser not found: {BROWSER}", file=sys.stderr)
        return False
    if not FONT_PATH.is_file():
        print(f"ERROR font not found: {FONT_PATH}", file=sys.stderr)
        return False

    subject, cards = build_cards(ep)
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    stage_root = Path(
        tempfile.mkdtemp(prefix=f".render-staging-{ep}-", dir=SCRIPT_DIR)
    )
    stage_png = stage_root / "png"
    stage_png.mkdir()
    stage_gallery = stage_root / f"{ep}-cards.html"
    stage_manifest = stage_root / f"{ep}-card-manifest.json"
    temp_html = stage_root / f"_render_tmp_{ep}.html"
    user_data = stage_root / "edge-profile"
    ok: list[str] = []
    try:
        for name, html in cards:
            temp_html.write_text(html, encoding="utf-8")
            preflight_ok, preflight_report = run_layout_preflight(
                temp_html,
                stage_root / f"edge-preflight-{name}",
            )
            if not preflight_ok:
                print(f"LAYOUT {name}: {preflight_report}", file=sys.stderr)
                print("FAIL " + name)
                continue
            png = stage_png / f"{name}.png"
            command = [
                str(BROWSER),
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--no-first-run",
                "--no-default-browser-check",
                "--allow-file-access-from-files",
                "--user-data-dir=" + str(user_data),
                "--hide-scrollbars",
                "--force-device-scale-factor=2",
                "--virtual-time-budget=4000",
                "--screenshot=" + str(png),
                "--window-size=1080,1440",
                temp_html.as_uri(),
            ]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=35,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                result = None

            success = (
                result is not None
                and result.returncode == 0
                and wait_for_file(png)
                and png_dimensions(png) == (2160, 2880)
            )
            print(("PNG  " if success else "FAIL ") + name)
            if success:
                ok.append(name)
        if len(ok) != len(cards):
            print(f"DONE {len(ok)}/{len(cards)} PNG")
            return False

        write_gallery(ep, subject, cards, stage_gallery)
        write_manifest(
            ep,
            subject,
            cards,
            stage_png,
            stage_gallery,
            stage_manifest,
            "rendered",
        )
        validate_staged_episode(
            ep,
            subject,
            cards,
            stage_png,
            stage_gallery,
            stage_manifest,
        )
        commit_staged_episode(
            ep,
            SCRIPT_DIR,
            PNG_DIR,
            stage_png,
            stage_gallery,
            stage_manifest,
        )
        print(f"DONE {len(ok)}/{len(cards)} PNG")
        return True
    except (OSError, RuntimeError) as exc:
        print(
            f"ERROR episode {ep} not committed; old artifacts preserved: {exc}",
            file=sys.stderr,
        )
        return False
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)


def usage() -> str:
    ids = "|".join(sorted(EPISODES))
    return (
        f"Usage: python render_cards.py [{ids}|all] ...\n"
        "       python render_cards.py --manifest-only <episode>\n"
        "       python render_cards.py --reconstruct-manifest <episode>\n"
        "       python render_cards.py --validate-manifest <episode>\n"
        "No argument renders the first registered episode; --list prints episode IDs.\n"
        "FEYNMAN_NOTES_EDGE may point to a Chromium browser executable.\n"
        "FEYNMAN_NOTES_SKILL_DIR may point to an installed feynman-notes folder."
    )


def select_episodes(args: list[str]) -> list[str]:
    for registered in EPISODES:
        validate_episode_id(registered)
    if not args:
        return [sorted(EPISODES)[0]]
    if args == ["all"]:
        return sorted(EPISODES)
    if "all" in args:
        raise ValueError("'all' 不能与具体 episode 同时使用")

    selected: list[str] = []
    for ep in args:
        if ep not in EPISODES:
            raise ValueError(f"未知 episode: {ep}")
        if ep in selected:
            raise ValueError(f"duplicate episode: {ep}")
        selected.append(ep)
    return selected


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--list"]:
        for ep in sorted(EPISODES):
            print(f"{ep}\t{EPISODES[ep]['subject']}")
        return 0
    if any(arg in {"-h", "--help"} for arg in args):
        print(usage())
        return 0
    if len(args) == 2 and args[0] in {"--manifest-only", "--reconstruct-manifest"}:
        ep = args[1]
        if ep not in EPISODES:
            print(f"ERROR 未知 episode: {ep}\n{usage()}", file=sys.stderr)
            return 2
        return 0 if reconstruct_manifest(ep) else 1
    if len(args) == 2 and args[0] == "--validate-manifest":
        ep = args[1]
        if ep not in EPISODES:
            print(f"ERROR 未知 episode: {ep}\n{usage()}", file=sys.stderr)
            return 2
        return 0 if validate_formal_manifest(ep) else 1
    try:
        selected = select_episodes(args)
    except ValueError as exc:
        print(f"ERROR {exc}\n{usage()}", file=sys.stderr)
        return 2

    all_ok = True
    for ep in selected:
        try:
            episode_ok = render_episode(ep)
        except Exception as exc:
            print(
                f"ERROR episode {ep} failed; continuing remaining episodes: {exc}",
                file=sys.stderr,
            )
            episode_ok = False
        if not episode_ok:
            all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
