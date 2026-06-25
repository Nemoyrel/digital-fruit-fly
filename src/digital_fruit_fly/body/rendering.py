from __future__ import annotations

import importlib
from dataclasses import dataclass

from digital_fruit_fly.runtime.timeouts import JsonObject


@dataclass(frozen=True)
class RendererSelection:
    requested: str
    effective: str
    headless: bool

    def to_json(self) -> JsonObject:
        return {
            "requested": self.requested,
            "effective": self.effective,
            "headless": self.headless,
        }


def prepare_glfw_platform(headless: bool, renderer: str) -> JsonObject:
    if not should_request_glfw_null_platform(headless, renderer):
        return {"platform_hint": "default", "reason": "windowed"}
    glfw = importlib.import_module("glfw")
    glfw.init_hint(glfw.PLATFORM, glfw.PLATFORM_NULL)
    reason = "headless" if headless else "renderer_none"
    return {"platform_hint": "null", "reason": reason}


def select_renderer(headless: bool, renderer: str) -> RendererSelection:
    effective = "none" if headless and renderer == "auto" else renderer
    return RendererSelection(requested=renderer, effective=effective, headless=headless)


def should_request_glfw_null_platform(headless: bool, renderer: str) -> bool:
    return headless or renderer == "none"
