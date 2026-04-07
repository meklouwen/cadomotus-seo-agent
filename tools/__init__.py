from tools.gsc import GSC_TOOLS, execute_gsc_tool
from tools.shopify import SHOPIFY_TOOLS, execute_shopify_tool
from tools.gmail import GMAIL_TOOLS, execute_gmail_tool
from tools.pagespeed import PAGESPEED_TOOLS, execute_pagespeed_tool

ALL_TOOLS = GSC_TOOLS + SHOPIFY_TOOLS + GMAIL_TOOLS + PAGESPEED_TOOLS

TOOL_EXECUTORS = {}
for t in GSC_TOOLS:
    TOOL_EXECUTORS[t["name"]] = execute_gsc_tool
for t in SHOPIFY_TOOLS:
    TOOL_EXECUTORS[t["name"]] = execute_shopify_tool
for t in GMAIL_TOOLS:
    TOOL_EXECUTORS[t["name"]] = execute_gmail_tool
for t in PAGESPEED_TOOLS:
    TOOL_EXECUTORS[t["name"]] = execute_pagespeed_tool
