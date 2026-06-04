"""Shared Streamlit chrome for the UI pages."""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st


_ROOT = Path(__file__).resolve().parents[2]
_LOGO_PATH = _ROOT / ".github" / "images" / "logo.svg"


def _logo_data_uri() -> str:
    svg_bytes = _LOGO_PATH.read_bytes()
    encoded = base64.b64encode(svg_bytes).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def apply_chatgpt_style() -> None:
    """Apply a restrained ChatGPT-like shell around Streamlit pages."""
    st.markdown(
        """
<style>
:root {
  --opentax-navy: #112052;
  --opentax-sky: #112052;
  --opentax-white: #FFFFFF;
  --opentax-sidebar: #F8FBFF;
  --opentax-sidebar-muted: rgba(17, 32, 82, 0.58);
  --opentax-sidebar-active: rgba(17, 32, 82, 0.10);
  --opentax-border: rgba(17, 32, 82, 0.10);
  --opentax-main: #FFFFFF;
  --opentax-text: #112052;
  color-scheme: light;
}

html,
body,
.stApp {
  color-scheme: light;
}

div[data-testid="stSidebar"] {
  background: var(--opentax-sidebar);
  color: var(--opentax-navy);
  border-right: 1px solid var(--opentax-border);
}

section[data-testid="stSidebar"] {
  background: var(--opentax-sidebar) !important;
  color: var(--opentax-navy);
  border-right: 1px solid var(--opentax-border);
}

div[data-testid="stSidebar"] > div {
  background: var(--opentax-sidebar);
  padding-top: 14px;
}

section[data-testid="stSidebar"] > div {
  background: var(--opentax-sidebar) !important;
  padding-top: 14px;
}

div[data-testid="stSidebarNav"] {
  display: none;
}

section[data-testid="stSidebarNav"],
nav[data-testid="stSidebarNav"],
div[data-testid="stSidebarNav"],
div[data-testid="stSidebarNavItems"],
div[data-testid="stSidebarNavSeparator"],
div[data-testid="stSidebarNavLinkContainer"],
div[data-testid="stSidebarNavLink"] {
  display: none !important;
}

div[data-testid="stDecoration"],
div[data-testid="stStatusWidget"],
div[data-testid="stAppDeployButton"],
div[data-testid="stMainMenu"] {
  visibility: hidden;
}

div[data-testid="stSidebarCollapseButton"],
div[data-testid="stSidebarCollapsedControl"] {
  visibility: visible !important;
  opacity: 1 !important;
}

section[data-testid="stSidebar"] div[data-testid="stSidebarHeader"] {
  height: 44px;
  min-height: 44px;
  align-items: center;
  padding-bottom: 0;
}

section[data-testid="stSidebar"] div[data-testid="stSidebarCollapseButton"] {
  align-self: center;
}

div[data-testid="stSidebar"] .stMarkdown,
div[data-testid="stSidebar"] label,
div[data-testid="stSidebar"] p,
div[data-testid="stSidebar"] span {
  color: var(--opentax-navy);
}

section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span {
  color: var(--opentax-navy);
}

div[data-testid="stSidebar"] .stCaptionContainer,
div[data-testid="stSidebar"] .stCaptionContainer p {
  color: var(--opentax-sidebar-muted) !important;
}

section[data-testid="stSidebar"] .stCaptionContainer,
section[data-testid="stSidebar"] .stCaptionContainer p {
  color: var(--opentax-sidebar-muted) !important;
}

div[data-testid="stSidebar"] hr {
  border-color: var(--opentax-border);
  margin: 14px 0;
}

section[data-testid="stSidebar"] hr {
  border-color: var(--opentax-border);
  margin: 14px 0;
}

div[data-testid="stSidebar"] button {
  border-radius: 8px;
  border-color: var(--opentax-border);
  background: var(--opentax-white);
  color: var(--opentax-text);
}

section[data-testid="stSidebar"] button {
  border-radius: 8px;
  border-color: var(--opentax-border);
  background: var(--opentax-white);
  color: var(--opentax-navy);
}

div[data-testid="stSidebar"] .stButton,
section[data-testid="stSidebar"] .stButton {
  margin-bottom: 0;
}

div[data-testid="stSidebar"] .stButton > button,
section[data-testid="stSidebar"] .stButton > button {
  min-height: 36px;
  padding-top: 6px;
  padding-bottom: 6px;
}

div[data-testid="stSidebar"] [data-testid="stBaseButton-primary"],
section[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"][kind="primary"],
div[data-testid="stSidebar"] button[kind="primary"],
div[data-testid="stSidebar"] .stButton > button[kind="primary"] {
  background: var(--opentax-sky) !important;
  color: var(--opentax-white) !important;
  border-color: var(--opentax-sky) !important;
}

div[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] p,
div[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] span {
  color: var(--opentax-white) !important;
}

[data-testid="stBaseButton-primary"],
button[data-testid="stBaseButton-primary"][kind="primary"],
.stButton > button[kind="primary"] {
  color: var(--opentax-white) !important;
}

[data-testid="stBaseButton-primary"] p,
[data-testid="stBaseButton-primary"] span,
.stButton > button[kind="primary"] p,
.stButton > button[kind="primary"] span {
  color: var(--opentax-white) !important;
}

.opentax-logo {
  display: flex;
  align-items: center;
  height: 44px;
  width: 158px;
  margin: 0;
  padding: 0;
  position: fixed;
  top: 14px;
  left: 22px;
  z-index: 30;
  pointer-events: none;
}

.opentax-logo-card {
  width: 100%;
  box-sizing: border-box;
  background: transparent;
  border: 0;
  padding: 0;
}

.opentax-logo-card img {
  display: block;
  width: min(118px, 100%);
  height: auto;
}

.opentax-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: -24px;
  margin-bottom: 24px;
}

.opentax-nav a {
  display: flex;
  align-items: center;
  min-height: 38px;
  padding: 8px 10px;
  border-radius: 8px;
  color: var(--opentax-navy) !important;
  text-decoration: none;
  font-size: 14px;
  line-height: 1.2;
}

.opentax-nav a:hover,
.opentax-nav a.active {
  background: var(--opentax-sidebar-active);
  color: var(--opentax-navy) !important;
}

.opentax-sidebar-label {
  color: var(--opentax-sidebar-muted);
  font-size: 12px;
  font-weight: 600;
  margin: 14px 0 8px 2px;
}

.opentax-sidebar-footer {
  position: fixed;
  left: 24px;
  bottom: 18px;
  width: min(236px, calc(100vw - 48px));
  z-index: 5;
}

.opentax-sidebar-footer .opentax-sidebar-label {
  margin-top: 0;
}

.opentax-sidebar-footer p {
  margin-bottom: 0;
}

.opentax-case-summary-slot {
  min-height: 46px;
}

.opentax-case-summary {
  box-sizing: border-box;
  width: 100%;
  min-height: 46px;
  padding: 12px 16px;
  border-radius: 8px;
  background: #E7F0FF;
  color: var(--opentax-navy);
  font-size: 14px;
  font-weight: 700;
  line-height: 1.4;
  overflow-wrap: anywhere;
  display: flex;
  align-items: center;
  gap: 4px;
}

.opentax-case-summary span {
  font-weight: 600;
}

div[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"]:has(.opentax-case-summary),
section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"]:has(.opentax-case-summary),
div[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"]:has(.opentax-case-summary-slot),
section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"]:has(.opentax-case-summary-slot) {
  margin-bottom: 0;
}

div[data-testid="stSidebar"] div[data-testid="stAlert"],
section[data-testid="stSidebar"] div[data-testid="stAlert"] {
  box-sizing: border-box;
}

div[data-testid="stSidebar"] div[data-testid="stAlert"] p,
section[data-testid="stSidebar"] div[data-testid="stAlert"] p {
  margin-bottom: 0;
}

div[data-testid="stSidebar"] .st-key-case_generator_block,
section[data-testid="stSidebar"] .st-key-case_generator_block {
  padding-bottom: 18px;
}

div[data-testid="stSidebar"] div:has(> .st-key-case_generator_block),
section[data-testid="stSidebar"] div:has(> .st-key-case_generator_block) {
  margin-top: auto !important;
}

div[data-testid="stSidebar"] div[data-testid="stVerticalBlock"]:has(.st-key-case_generator_block),
section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"]:has(.st-key-case_generator_block) {
  min-height: calc(100vh - 116px);
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  overflow: visible;
}

.stApp {
  background: var(--opentax-main);
}

.opentax-empty-chat {
  position: fixed;
  top: 50%;
  left: calc(50% + 150px);
  width: min(920px, 76vw);
  height: min(640px, 62vh);
  transform: translate(-50%, -50%);
  pointer-events: none;
  z-index: 1;
  opacity: 0.82;
  filter: blur(34px) saturate(122%);
  background:
    radial-gradient(circle at 50% 48%, rgba(115, 201, 255, 0.58) 0%, rgba(115, 201, 255, 0.32) 22%, transparent 58%),
    radial-gradient(circle at 30% 62%, rgba(115, 201, 255, 0.28) 0%, transparent 44%),
    radial-gradient(circle at 72% 36%, rgba(17, 32, 82, 0.13) 0%, transparent 38%),
    conic-gradient(from 120deg at 50% 50%, transparent 0deg, rgba(115, 201, 255, 0.28) 82deg, transparent 168deg, rgba(115, 201, 255, 0.20) 250deg, transparent 360deg);
  animation: opentax-diffuse 8s ease-in-out infinite alternate;
}

.stApp:has(.opentax-empty-chat) div[data-testid="stSidebar"],
.stApp:has(.opentax-empty-chat) section[data-testid="stSidebar"] {
  position: relative;
  z-index: 20;
}

@keyframes opentax-diffuse {
  0% {
    transform: translate(-50%, -50%) scale(0.88) rotate(-2deg);
    border-radius: 46% 54% 52% 48%;
  }

  55% {
    transform: translate(-50%, -50%) scale(1.04) rotate(3deg);
    border-radius: 58% 42% 46% 54%;
  }

  100% {
    transform: translate(-50%, -50%) scale(1.16) rotate(-1deg);
    border-radius: 50% 50% 58% 42%;
  }
}

.opentax-empty-chat-title {
  position: fixed;
  top: calc(50vh - 54px);
  left: calc(50% + 150px);
  transform: translateX(-50%);
  width: min(760px, calc(100vw - 360px));
  max-width: 760px;
  margin: 0;
  padding: 0 !important;
  text-align: center;
  color: var(--opentax-navy);
  font-size: 22px !important;
  font-weight: 700;
  line-height: 1.35;
  letter-spacing: 0;
  z-index: 3;
}

.stApp:has(.opentax-empty-chat) div[data-testid="stChatInput"] {
  position: fixed !important;
  bottom: auto !important;
  top: calc(50vh + 4px) !important;
  left: calc(50% + 150px) !important;
  transform: translateX(-50%);
  width: min(760px, calc(100vw - 360px));
  max-width: 760px;
  z-index: 3;
}

@media (max-width: 900px) {
  .opentax-empty-chat {
    left: 50% !important;
    width: min(680px, 96vw);
    height: min(560px, 58vh);
  }

  .opentax-empty-chat-title {
    left: 50% !important;
    width: min(760px, calc(100vw - 32px));
  }

  .stApp:has(.opentax-empty-chat) div[data-testid="stChatInput"] {
    left: 50% !important;
    width: min(760px, calc(100vw - 32px));
  }
}

h1, h2, h3 {
  color: var(--opentax-navy) !important;
}

a {
  color: var(--opentax-navy);
}

div[data-testid="stChatInput"] textarea {
  background: var(--opentax-sidebar) !important;
  color: var(--opentax-navy) !important;
  border-color: rgba(17, 32, 82, 0.14) !important;
  box-shadow: 0 10px 28px rgba(17, 32, 82, 0.06);
}

div[data-testid="stChatInput"] textarea::placeholder {
  color: rgba(17, 32, 82, 0.48) !important;
}

div[data-testid="stChatInput"] > div,
div[data-testid="stChatInput"] div:has(> textarea) {
  background: var(--opentax-sidebar) !important;
  border-color: rgba(17, 32, 82, 0.14) !important;
}

div[data-testid="stChatInput"] button {
  background: var(--opentax-sky);
  color: var(--opentax-white);
}

.main .block-container {
  max-width: 980px;
  padding-top: 36px;
  padding-bottom: 72px;
}

div[data-testid="stChatMessage"] {
  background: transparent;
  border: 0;
}

div[data-testid="stChatInput"] {
  max-width: 900px;
  margin: 0 auto;
  background: transparent;
}
</style>
""",
        unsafe_allow_html=True,
    )


def render_sidebar_nav(active: str) -> None:
    """Render the top logo and app navigation links."""
    app_class = "active" if active == "chat" else ""
    settings_class = "active" if active == "settings" else ""
    logo_src = _logo_data_uri()
    st.markdown(
        f"""
<div class="opentax-logo">
  <div class="opentax-logo-card">
    <img src="{logo_src}" alt="OpenTax">
  </div>
</div>
<nav class="opentax-nav">
  <a class="{app_class}" href="/" target="_self">새 채팅</a>
  <a class="{settings_class}" href="/admin" target="_self">설정</a>
</nav>
""",
        unsafe_allow_html=True,
    )
