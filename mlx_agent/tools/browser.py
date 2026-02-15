"""
浏览器自动化工具 - 延迟导入版本

使用 Playwright 进行浏览器控制
"""

from typing import List, Optional, Any
import asyncio

from loguru import logger

from .base import BaseTool, ToolCategory, ToolParameter, ToolResult, register_tool


@register_tool
class BrowserTool(BaseTool):
    """浏览器自动化工具 - 延迟导入版本，带反爬配置"""

    name = "browser"
    description = "控制浏览器进行网页操作：访问、点击、输入、截图等（带反爬配置）"
    category = ToolCategory.BROWSER

    # 反爬配置
    STEALTH_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    
    STEALTH_VIEWPORT = {"width": 1920, "height": 1080}
    
    BROWSER_LAUNCH_ARGS = [
        '--disable-blink-features=AutomationControlled',
        '--disable-web-security',
        '--disable-features=IsolateOrigins,site-per-process',
        '--disable-dev-shm-usage',
        '--disable-setuid-sandbox',
        '--no-sandbox',
        '--disable-accelerated-2d-canvas',
        '--disable-gpu',
        '--window-size=1920,1080',
    ]
    
    STEALTH_SCRIPTS = [
        # 隐藏 webdriver 属性
        """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        """,
        # 覆盖 plugins
        """
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        """,
        # 覆盖 languages
        """
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en']
        });
        """,
        # 覆盖 chrome 属性
        """
        window.chrome = {
            runtime: {}
        };
        """,
        # 覆盖 notification permission
        """
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        """,
    ]

    def __init__(self):
        super().__init__()
        self._playwright_available = None

    def _check_playwright(self) -> bool:
        """检查 Playwright 是否可用"""
        if self._playwright_available is None:
            try:
                import playwright  # noqa: F401
                self._playwright_available = True
            except ImportError:
                self._playwright_available = False
        return self._playwright_available

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                description="操作类型: navigate(访问), click(点击), input(输入), screenshot(截图), text(提取文本)",
                type="string",
                required=True,
                enum=["navigate", "click", "input", "screenshot", "text", "scroll"]
            ),
            ToolParameter(
                name="url",
                description="网页 URL (navigate 时必需)",
                type="string",
                required=False
            ),
            ToolParameter(
                name="selector",
                description="CSS 选择器 (click/input 时必需)",
                type="string",
                required=False
            ),
            ToolParameter(
                name="text",
                description="输入文本 (input 时必需)",
                type="string",
                required=False
            ),
            ToolParameter(
                name="wait_for",
                description="等待元素出现的选择器",
                type="string",
                required=False
            )
        ]

    async def execute(self, **params) -> ToolResult:
        action = params.get("action")
        
        # 检查是否使用反爬模式
        use_stealth = params.get("stealth", True)

        # 提前检查 Playwright 是否可用
        if not self._check_playwright():
            return ToolResult(
                success=False,
                output=None,
                error="Playwright not installed. Run: pip install playwright && playwright install chromium"
            )

        try:
            # 延迟导入 Playwright
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                # 使用反爬配置启动浏览器
                if use_stealth:
                    browser = await self._launch_browser_stealth(p)
                else:
                    browser = await p.chromium.launch(headless=True)
                    
                # 创建带反爬配置的上下文
                if use_stealth:
                    context = await self._create_context_stealth(browser)
                else:
                    context = await browser.new_context(
                        viewport={"width": 1280, "height": 720}
                    )
                
                page = await context.new_page()

                try:
                    if action == "navigate":
                        return await self._navigate(page, params)
                    elif action == "click":
                        return await self._click(page, params)
                    elif action == "input":
                        return await self._input(page, params)
                    elif action == "screenshot":
                        return await self._screenshot(page, params)
                    elif action == "text":
                        return await self._extract_text(page, params)
                    elif action == "scroll":
                        return await self._scroll(page, params)
                    else:
                        return ToolResult(
                            success=False,
                            output=None,
                            error=f"Unknown action: {action}"
                        )
                finally:
                    await browser.close()

        except Exception as e:
            logger.error(f"Browser action failed: {e}")
            return ToolResult(
                success=False,
                output=None,
                error=str(e)
            )
    
    async def _launch_browser_stealth(self, playwright) -> Any:
        """使用反爬配置启动浏览器"""
        return await playwright.chromium.launch(
            headless=True,
            args=self.BROWSER_LAUNCH_ARGS
        )
    
    async def _create_context_stealth(self, browser) -> Any:
        """创建带反爬配置的浏览器上下文"""
        context = await browser.new_context(
            viewport=self.STEALTH_VIEWPORT,
            user_agent=self.STEALTH_USER_AGENT,
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            extra_http_headers={
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            }
        )
        
        # 注入 stealth 脚本
        for script in self.STEALTH_SCRIPTS:
            await context.add_init_script(script)
        
        return context

    async def _navigate(self, page, params) -> ToolResult:
        url = params.get("url")
        if not url:
            return ToolResult(success=False, output=None, error="URL required")

        await page.goto(url, wait_until="networkidle")
        title = await page.title()

        return ToolResult(
            success=True,
            output={
                "url": page.url,
                "title": title
            }
        )

    async def _click(self, page, params) -> ToolResult:
        selector = params.get("selector")
        if not selector:
            return ToolResult(success=False, output=None, error="Selector required")

        await page.click(selector)

        return ToolResult(
            success=True,
            output={"clicked": selector}
        )

    async def _input(self, page, params) -> ToolResult:
        selector = params.get("selector")
        text = params.get("text")
        if not selector or text is None:
            return ToolResult(success=False, output=None, error="Selector and text required")

        await page.fill(selector, text)

        return ToolResult(
            success=True,
            output={"input": text, "selector": selector}
        )

    async def _screenshot(self, page, params) -> ToolResult:
        # 延迟导入 base64
        import base64

        screenshot_bytes = await page.screenshot(full_page=True)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return ToolResult(
            success=True,
            output={
                "screenshot_base64": screenshot_b64,
                "format": "png"
            }
        )

    async def _extract_text(self, page, params) -> ToolResult:
        # 提取页面正文
        text = await page.evaluate('''() => {
            const article = document.querySelector('article') || document.querySelector('main') || document.body;
            return article.innerText;
        }''')

        return ToolResult(
            success=True,
            output={
                "text": text[:5000],
                "length": len(text)
            }
        )

    async def _scroll(self, page, params) -> ToolResult:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        return ToolResult(
            success=True,
            output={"scrolled": True}
        )
