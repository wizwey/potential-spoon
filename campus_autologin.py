import asyncio
import logging
import os
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import Browser, Page, async_playwright


load_dotenv(Path(__file__).with_name(".env"))

PORTAL_URL = os.getenv("PORTAL_URL", "http://10.255.255.154/")
USERNAME = os.getenv("USERNAME", "").strip()
PASSWORD = os.getenv("PASSWORD", "")
HEADLESS = os.getenv("HEADLESS", "true").lower() not in {"0", "false", "no"}
CHECK_INTERVAL = max(5, int(os.getenv("CHECK_INTERVAL", "30")))
RETRY_INTERVAL = max(3, int(os.getenv("RETRY_INTERVAL", "10")))
CONNECTIVITY_URL = os.getenv("CONNECTIVITY_URL", "http://connectivitycheck.gstatic.com/generate_204")
BROWSER_EXECUTABLE = os.getenv("BROWSER_EXECUTABLE", "").strip()
WIFI_NAME = os.getenv("WIFI_NAME", "").strip()
NETWORK_PROVIDER = os.getenv("NETWORK_PROVIDER", "").strip()

USER_SELECTOR = os.getenv("USER_SELECTOR", "").strip()
PASS_SELECTOR = os.getenv("PASS_SELECTOR", "").strip()
SUBMIT_SELECTOR = os.getenv("SUBMIT_SELECTOR", "").strip()


def find_installed_browser() -> str | None:
    if BROWSER_EXECUTABLE and Path(BROWSER_EXECUTABLE).exists():
        return BROWSER_EXECUTABLE
    candidates = [
        shutil.which("chrome"),
        shutil.which("msedge"),
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(x86)%\Microsoft\Edge\Application\msedge.exe"),
    ]
    return next((path for path in candidates if path and Path(path).exists()), None)


def first_visible(page: Page, selectors: list[str]):
    return page.locator(", ".join(selectors)).filter(visible=True).first


async def fill_login_form(page: Page) -> None:
    user = page.locator(USER_SELECTOR) if USER_SELECTOR else first_visible(page, [
        'input[type="text"]', 'input[type="email"]', 'input[name*="user" i]',
        'input[id*="user" i]', 'input[placeholder*="账号" i]', 'input[placeholder*="用户名" i]'
    ])
    password = page.locator(PASS_SELECTOR) if PASS_SELECTOR else first_visible(page, [
        'input[type="password"]', 'input[name*="pass" i]', 'input[id*="pass" i]',
        'input[placeholder*="密码" i]'
    ])
    await user.fill(USERNAME)
    await password.fill(PASSWORD)

    if NETWORK_PROVIDER:
        selects = page.locator("select")
        for index in range(await selects.count()):
            select = selects.nth(index)
            if not await select.is_visible():
                continue
            try:
                await select.select_option(label=NETWORK_PROVIDER)
                logging.info("已选择运营商：%s", NETWORK_PROVIDER)
                break
            except Exception:
                continue

    if SUBMIT_SELECTOR:
        await page.locator(SUBMIT_SELECTOR).click()
    else:
        selectors = [
            'button[type="submit"]', 'input[type="submit"]',
            'button:has-text("登录")', 'input[value*="登录"]',
            'a:has-text("登录")', '[onclick]:has-text("登录")',
            'button:has-text("认证")', 'a:has-text("认证")'
        ]
        clicked = False
        for selector in selectors:
            candidates = page.locator(selector)
            for index in range(await candidates.count()):
                candidate = candidates.nth(index)
                if await candidate.is_visible():
                    await candidate.click(force=True)
                    logging.info("已点击门户登录按钮：%s", selector)
                    clicked = True
                    break
            if clicked:
                break
        if not clicked:
            logging.warning("未识别到登录按钮，尝试在密码框按回车提交")
            await password.press("Enter")


async def portal_is_reachable(page: Page) -> bool:
    try:
        response = await page.request.get(
            CONNECTIVITY_URL, timeout=8000, max_redirects=0
        )
        # generate_204 只有真正接入公网时才应返回 204。
        # 登录页劫持或重定向得到 200/30x，不能视作联网成功。
        return response.status == 204
    except Exception:
        return False


def reconnect_wifi() -> None:
    if not WIFI_NAME or os.name != "nt":
        return
    try:
        result = subprocess.run(
            ["netsh", "wlan", "connect", f"name={WIFI_NAME}"],
            capture_output=True,
            text=True,
            encoding="mbcs",
            errors="replace",
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0:
            logging.info("已请求 Windows 连接 Wi-Fi：%s", WIFI_NAME)
        else:
            logging.warning("Wi-Fi 重连失败，请确认系统已保存该网络：%s", WIFI_NAME)
    except Exception as exc:
        logging.warning("无法执行 Wi-Fi 重连：%s", exc)


async def login_once(browser: Browser) -> bool:
    context = await browser.new_context()
    page = await context.new_page()
    try:
        if await portal_is_reachable(page):
            logging.info("公网连接正常，无需重新登录")
            return True

        reconnect_wifi()
        if WIFI_NAME:
            await asyncio.sleep(5)
            if await portal_is_reachable(page):
                logging.info("Wi-Fi 已恢复且公网连接正常")
                return True

        await page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=20000)
        # 不能用“没有密码框”判断联网，否则错误页也会被当作成功。
        if not await page.locator('input[type="password"]').count():
            logging.warning("门户已打开，但未识别到密码框；不会误判为联网成功")
            return False
        await fill_login_form(page)
        await page.wait_for_timeout(5000)
        logging.info("已提交登录请求，当前页面：%s", page.url)
        body_text = (await page.locator("body").inner_text()).lower()
        if any(word in body_text for word in ("密码错误", "账号不存在", "认证失败", "登录失败")):
            logging.error("门户返回了登录失败提示，请检查账号密码")
            return False
        return await portal_is_reachable(page)
    except Exception as exc:
        logging.warning("登录失败：%s", exc)
        return False
    finally:
        await context.close()


async def main() -> None:
    if not USERNAME or not PASSWORD or "请填写" in USERNAME:
        raise SystemExit("请先复制 .env.example 为 .env，并填写 USERNAME、PASSWORD")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    async with async_playwright() as playwright:
        executable = find_installed_browser()
        launch_options = {"headless": HEADLESS}
        if executable:
            logging.info("使用已安装的浏览器：%s", executable)
            launch_options["executable_path"] = executable
        else:
            logging.info("未找到系统浏览器，将使用 Playwright Chromium")
        browser = await playwright.chromium.launch(**launch_options)
        try:
            while True:
                if await login_once(browser):
                    logging.info("网络检测正常，%s 秒后再次检查", CHECK_INTERVAL)
                    await asyncio.sleep(CHECK_INTERVAL)
                else:
                    logging.info("网络未连接，%s 秒后重试", RETRY_INTERVAL)
                    await asyncio.sleep(RETRY_INTERVAL)
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
