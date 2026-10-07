# Interactive geographic navigation (A7.1)

The existing Feed loads a locally vendored **MapLibre GL JS 5.10.0** bundle.
No framework, build step, account, API key or CDN is required. Its BSD-3-Clause
license and bundled notices are in `ui/vendor/MAPLIBRE-LICENSE.txt`.

Bundle origin: `https://registry.npmjs.org/maplibre-gl/-/maplibre-gl-5.10.0.tgz`.
SHA256: JS `06ce45475856ffd058aca70ae9f579adcb52754e501cc8620e9f1c7e544156bd`;
CSS `43c1d886b5fdf0aac4e7135bd6f84b823d9f48283a648012665f9be52c01389f`.

The basemap uses `https://tiles.openfreemap.org/styles/liberty` and its referenced
vector tiles, fonts and sprites. These are the only external map dependencies.
Required OpenFreeMap / OpenMapTiles / OpenStreetMap attribution remains visible.
Provider access is a browser dependency, not an API or event-feed dependency.

Library failure, unavailable WebGL, a map error or a bounded load timeout returns
to the existing offline SVG and event list. There is no automatic map retry on
that page. Reloading the page is a user action. No stack traces are displayed.

Markers retain separate roles: source-supported event location (circle), inferred
context geography (ring), institution reference (diamond). A context centroid is
never reverse-geocoded into a country. Global and MULTI_REGION use unpinned lists.
Markers aggregate by semantic region/reference; popups show at most three events
and a remaining count. Desktop hover, keyboard focus and mobile tap open the same
popup. Selecting an event focuses, scrolls to and expands the existing card.
Popup text is inserted with DOM `textContent`, not interpreted as HTML.

Country boundary hover is deferred. Country labels/coastlines come from the
provider style and are available only when the real basemap loads. No claim of
real basemap acceptance should be made from a synthetic style test.
The initial zoom adapts to viewport width. Nearby reference anchors can overlap
at world overview; zoom, keyboard focus and the accessible region/event list
remain alternatives. No coordinate jitter or false country assignment is used.
