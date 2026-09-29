from __future__ import annotations

import re
from urllib.parse import urlsplit

from playwright.sync_api import Page, expect

from conftest import open_dashboard


SECTIONS = [
    ("نظرة عامة", "نظرة عامة"),
    ("المراقبة الحية", "المراقبة الحية"),
    ("المقاطع التجريبية", "المقاطع التجريبية"),
    ("الحوادث", "ملفات الحوادث"),
    ("التحليل الذكي", "التحليل"),
    ("العمليات", "غرفة"),
    ("النظام", "حالة"),
]


def rail_label(page: Page, index: int) -> str:
    value = page.locator(".rail-item").nth(index).get_attribute("title")
    assert value is not None
    return value


def test_navigation_keys_and_rail_visit_all_arabic_sections(page: Page, dev_server: str) -> None:
    # Arrange
    open_dashboard(page, dev_server)
    expect(page.locator("html")).to_have_attribute("dir", "rtl")
    expect(page.locator("html")).to_have_attribute("lang", "ar")
    assert page.evaluate("Array.from(document.querySelectorAll('.rail-item')).every((item) => /\\p{Script=Arabic}/u.test(item.title))")

    # Act / Assert: keyboard shortcuts and the rail both reach every section.
    for index, (_label, heading) in enumerate(SECTIONS, start=1):
        page.locator(".rail-item").first.click()
        page.evaluate("document.activeElement && document.activeElement.blur()")
        page.keyboard.press(str(index))
        expected_label = rail_label(page, index - 1)
        expect(page.locator(".rail-item[aria-current='page']")).to_have_attribute("title", expected_label)
        expect(page.locator(".topbar-location strong")).to_have_text(expected_label)
        expect(page.locator("main h1").first).to_contain_text(heading)
        page.locator(".rail-item").nth(index - 1).click()
        expect(page.locator(".topbar-location strong")).to_have_text(expected_label)


def test_fixture_banner_and_offline_state_are_honest(page: Page, dev_server: str) -> None:
    # Arrange / Act
    open_dashboard(page, dev_server, fixtures=True)

    # Assert fixture disclosure, then verify the non-fixture offline experience.
    expect(page.get_by_role("status").filter(has_text="بيانات تجريبية للمعاينة")).to_be_visible()
    open_dashboard(page, dev_server, fixtures=False)
    expect(page.locator(".fixture-banner")).to_have_count(0)
    expect(page.locator(".offline-panel")).to_be_visible()
    expect(page.locator(".offline-panel h2")).to_contain_text("الخادم غير متصل")
    expect(page.locator(".connection-indicator.status-online")).to_have_count(0)
    expect(page.locator(".state-live")).to_have_count(0)


def test_camera_cross_filter_updates_overview_incidents_and_clear(page: Page, dev_server: str) -> None:
    # Arrange
    open_dashboard(page, dev_server)
    expect(page.locator(".camera-row").first).to_be_visible()
    initial_kpi = page.locator(".overview-stat .stat-reading").first
    initial_count = int(initial_kpi.inner_text())

    # Act: select a camera, follow the shared filter into incidents, then clear it.
    camera_row = page.locator(".camera-row").first
    camera_id = camera_row.locator("bdi").first.inner_text()
    camera_count = int(camera_row.locator("bdi").last.inner_text())
    camera_row.click()

    # Assert overview KPI and filter chip reflect the selected camera.
    expect(page.locator(".active-filters")).to_contain_text(camera_id)
    filtered_kpi = page.locator(".overview-stat .stat-reading").first
    expect(filtered_kpi).to_have_text(str(camera_count))
    filtered_count = camera_count
    page.locator(".rail-item").nth(3).click()
    incident_rows = page.locator("button[data-alert-index]")
    expect(incident_rows).to_have_count(filtered_count)
    assert all(camera_id in (row.get_attribute("aria-label") or "") for row in incident_rows.all())
    page.get_by_role("button", name="مسح الكل").click()
    expect(page.locator(".active-filters")).to_have_count(0)
    expect(page.locator("button[data-alert-index]")).to_have_count(initial_count)


def test_incident_selection_and_jk_cursor_keep_the_same_dossier(page: Page, dev_server: str) -> None:
    # Arrange
    open_dashboard(page, dev_server)

    # Act: open the newest overview incident, then move and restore the queue cursor.
    page.locator(".latest-row").first.click()
    expect(page.locator(".topbar-location strong")).to_have_text("الحوادث")
    dossier = page.locator("main[aria-label='ملف الحادثة المحددة']")
    id_value = dossier.locator("dl bdi").last
    expect(id_value).to_be_visible()
    incident_id = id_value.inner_text()
    queue = page.locator("aside[aria-label='قائمة الحوادث']")
    expect(queue).to_contain_text(incident_id)
    cursor_id = queue.locator(".mt-2 bdi").first
    page.keyboard.press("j")
    expect(cursor_id).not_to_have_text(incident_id)
    page.keyboard.press("k")

    # Assert cursor returns to the selected incident and its dossier ID is unchanged.
    expect(queue).to_contain_text(incident_id)
    expect(id_value).to_have_text(incident_id)


def test_privacy_mode_hides_evidence_and_download_affordances(page: Page, dev_server: str) -> None:
    # Arrange
    open_dashboard(page, dev_server)
    page.locator(".latest-row").first.click()
    download_action = re.compile(r"evidence|download|تصدير|تنزيل|تحميل", re.IGNORECASE)
    expect(page.get_by_role("button", name=download_action).first).to_be_visible()

    # Act
    page.locator(".topbar-actions > .icon-action").nth(1).click()

    # Assert: any evidence/clip control still shown is disabled, so nothing can be exported.
    for control in page.get_by_role("button", name=download_action).all():
        expect(control).to_be_disabled()
    expect(page.locator("a[download]")).to_have_count(0)


def test_theme_persists_and_command_palette_navigates(page: Page, dev_server: str) -> None:
    # Arrange
    open_dashboard(page, dev_server)

    # Act: change the theme and reload, then open the command palette and navigate.
    page.get_by_role("button", name="تبديل المظهر").click()
    expect(page.locator("html")).to_have_class(re.compile(r"\blight\b"))
    page.reload(wait_until="domcontentloaded")
    page.locator("html[data-hydrated='true']").wait_for(state="attached")
    expect(page.locator("html")).to_have_class(re.compile(r"\blight\b"))
    page.keyboard.press("Control+k")
    dialog = page.get_by_role("dialog", name="لوحة الأوامر")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name=re.compile("الحوادث")).click()

    # Assert the palette closed and the requested section became active.
    expect(dialog).to_have_count(0)
    expect(page.locator(".topbar-location strong")).to_have_text("الحوادث")


def test_mobile_bottom_navigation_reaches_every_section_without_horizontal_scroll(page: Page, dev_server: str) -> None:
    # Arrange
    page.set_viewport_size({"width": 390, "height": 844})
    open_dashboard(page, dev_server)

    # Act / Assert
    for label, _heading in SECTIONS:
        index = SECTIONS.index((label, _heading))
        page.locator(".rail-item").nth(index).click()
        expected_label = rail_label(page, index)
        expect(page.locator(".rail-item[aria-current='page']")).to_have_attribute("title", expected_label)
        dimensions = page.evaluate("({width: window.innerWidth, body: document.body.scrollWidth, root: document.documentElement.scrollWidth})")
        assert dimensions["body"] <= dimensions["width"] and dimensions["root"] <= dimensions["width"], dimensions


def test_each_section_has_no_unexpected_console_errors(page: Page, dev_server: str) -> None:
    # Arrange: observe the initial load and every later section change.
    errors: list[tuple[str, str]] = []

    def capture_console_error(message) -> None:
        if message.type == "error":
            errors.append((message.text, message.location.get("url", "")))

    page.on("console", capture_console_error)
    page.on("pageerror", lambda error: errors.append((str(error), "")))
    open_dashboard(page, dev_server)

    # Act: visit every route surface through the visible rail.
    for label, _heading in SECTIONS:
        index = SECTIONS.index((label, _heading))
        page.locator(".rail-item").nth(index).click()
        expected_label = rail_label(page, index)
        expect(page.locator(".rail-item[aria-current='page']")).to_have_attribute("title", expected_label)
        expect(page.locator(".topbar-location strong")).to_have_text(expected_label)

    # Only requests to the API hosts explicitly blocked by the offline fixture are expected.
    expected_backend_origins = {"http://localhost:8002", "http://127.0.0.1:8002"}
    unexpected = [
        message
        for message, source_url in errors
        if f"{urlsplit(source_url).scheme}://{urlsplit(source_url).netloc}" not in expected_backend_origins
    ]
    assert not unexpected, "Unexpected browser console errors:\n" + "\n".join(unexpected)
