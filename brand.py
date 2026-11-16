"""
PunorAI Unified Brand Logo Component
------------------------------------
Extracts the exact PunorAI logo (SVG icon, multi-stop emerald/teal/lime gradient,
horizontal shimmer-sweep animation, and brand wordmark) into a reusable shared component.
Strictly matches the clean Landing Page navbar logo with centered icon and wordmark,
and NO subtitle underneath the brand name across all pages.

Provides:
- render_brand_logo(...) -> str: Generates complete HTML markup for the brand logo
- render_brand_icon(...) -> str: Generates the isolated SVG icon with linearGradient
- BrandLogo: Class wrapper providing .render(...) and <BrandLogo/> string representation
"""

def render_brand_icon(size: int = 26, id_prefix: str = "brand", extra_class: str = "") -> str:
    """Renders the standalone animated SVG icon with its dedicated multi-stop linear gradient."""
    grad_id = f"{id_prefix}LogoGrad"
    class_attr = f"brand-logo-icon {extra_class}".strip()
    return f"""<div class="{class_attr}">
  <svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="punor-logo-svg" aria-label="PunorAI Logo">
    <defs>
      <linearGradient id="{grad_id}" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stop-color="#10B981"/>
        <stop offset="60%" stop-color="#34D399"/>
        <stop offset="100%" stop-color="#B8D96B"/>
      </linearGradient>
    </defs>
    <circle cx="12" cy="12" r="9" stroke="url(#{grad_id})" stroke-width="2.2" stroke-linecap="round"/>
    <path d="M6.5 15.5C8 11.5 16 12.5 17.5 8.5" stroke="#10B981" stroke-width="2" stroke-linecap="round"/>
    <path d="M6.5 8.5C8 12.5 16 11.5 17.5 15.5" stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round" opacity="0.9"/>
    <circle cx="12" cy="12" r="2.2" fill="#B8D96B"/>
  </svg>
</div>"""


def render_brand_logo(
    href: str = "/",
    subtitle: str = "",  # Parameter ignored completely to enforce clean navbar match
    size: int = 26,
    extra_class: str = "",
    id_prefix: str = "brand",
    aria_label: str = "PunorAI",
    inline_styles: str = "",
    text_class: str = "",
    brand_name_style: str = "",
    show_sub: bool = False,  # Ignored completely
    **kwargs
) -> str:
    """
    Renders the unified PunorAI brand logo link component containing:
    1. Animated SVG icon with linearGradient (#10B981 -> #34D399 -> #B8D96B)
    2. Brand name wordmark with gradient clip text ("PunorAI")
    3. Strictly NO subtitle underneath the logo (matching Landing Page navbar)
    4. Shimmer sweep light-reflection animation and hover scale transition
    """
    grad_id = f"{id_prefix}LogoGrad"
    
    # Compose classes cleanly
    classes = ["punorai-brand-logo"]
    if extra_class:
        classes.append(extra_class)
    elif "brand-link" not in classes:
        classes.append("brand-link")
    full_class = " ".join(dict.fromkeys(" ".join(classes).split()))
    
    style_attr = f' style="{inline_styles}"' if inline_styles else ""
    name_style_attr = f' style="{brand_name_style}"' if brand_name_style else ""

    return f"""<!-- BrandLogo Component -->
<a href="{href}" class="{full_class}"{style_attr} aria-label="{aria_label}">
  <div class="brand-logo-icon">
    <svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="punor-logo-svg" aria-label="PunorAI Logo">
      <defs>
        <linearGradient id="{grad_id}" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stop-color="#10B981"/>
          <stop offset="60%" stop-color="#34D399"/>
          <stop offset="100%" stop-color="#B8D96B"/>
        </linearGradient>
      </defs>
      <circle cx="12" cy="12" r="9" stroke="url(#{grad_id})" stroke-width="2.2" stroke-linecap="round"/>
      <path d="M6.5 15.5C8 11.5 16 12.5 17.5 8.5" stroke="#10B981" stroke-width="2" stroke-linecap="round"/>
      <path d="M6.5 8.5C8 12.5 16 11.5 17.5 15.5" stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round" opacity="0.9"/>
      <circle cx="12" cy="12" r="2.2" fill="#B8D96B"/>
    </svg>
  </div>
  <div class="brand-name"{name_style_attr}>Punor<span>AI</span></div>
</a>"""


class BrandLogo:
    """Object representation of <BrandLogo/> component."""
    def __init__(self, href="/", subtitle="", size=26, extra_class="", id_prefix="brand", **kwargs):
        self.href = href
        self.size = size
        self.extra_class = extra_class
        self.id_prefix = id_prefix
        self.kwargs = kwargs

    def __str__(self) -> str:
        return render_brand_logo(
            href=self.href,
            size=self.size,
            extra_class=self.extra_class,
            id_prefix=self.id_prefix,
            **self.kwargs
        )

    def render(self) -> str:
        return str(self)
