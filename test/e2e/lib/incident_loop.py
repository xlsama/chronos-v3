from __future__ import annotations

import time

from playwright.sync_api import Page


def wait_for_incident_resolution(
    page: Page,
    ask_human_reply: str,
    timeout_ms: int = 8 * 60 * 1000,
) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    handled_approvals: set[str] = set()
    handled_questions: set[str] = set()

    while time.monotonic() < deadline:
        summary = page.locator('[data-testid="summary-section"]')
        try:
            if summary.is_visible():
                break
        except Exception:
            pass

        approval_card = page.locator('[data-testid="approval-card"]').last
        try:
            if approval_card.is_visible():
                approval_id = approval_card.get_attribute("data-approval-id") or "approval"
                if approval_id not in handled_approvals:
                    approve_btn = approval_card.locator('[data-testid="approve-button"]')
                    try:
                        if approve_btn.is_visible():
                            handled_approvals.add(approval_id)
                            approve_btn.click()
                            page.wait_for_timeout(2000)
                            continue
                    except Exception:
                        pass
        except Exception:
            pass

        ask_human_banner = page.locator('[data-testid="ask-human-banner"]')
        try:
            if ask_human_banner.is_visible():
                question = (ask_human_banner.text_content() or "").strip() or "ask-human"
                if question not in handled_questions:
                    handled_questions.add(question)
                    page.locator('[data-testid="prompt-textarea"]').fill(ask_human_reply)
                    page.locator('[data-testid="submit-incident"]').click()
                    page.wait_for_timeout(2000)
                    continue
        except Exception:
            pass

        page.wait_for_timeout(3000)
