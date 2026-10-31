"""Render Meridian's journal into a page on nikunjkaushik.com.

The safety property here is simple and worth stating: **the agent produces text,
this module produces HTML.** Every string from the model is escaped before it
reaches the page, so Meridian cannot inject markup, scripts, styles or links —
it can only say words. A compromised or confused agent gets a badly-written
journal entry, not a compromised website.

Two audiences, kept apart. The agent writes `summary` and `thoughts` for Nikunj in
private over Telegram, and `public_title` and `public_body` for this page. **Only the
public fields are rendered here**, and an entry with no public title is skipped
entirely, so a blunt private note cannot leak onto his professional site by accident.
"""

from __future__ import annotations

import datetime as dt
import html
import re
from pathlib import Path

from agent import memory

SITE = Path.home() / "Documents" / "GitHub" / "nikunjkaushik.com"

#: The subdomain's document root. Hostgator maps meridian.nikunjkaushik.com to
#: public_html/meridian, and the deploy action uploads this repo into public_html,
#: so a `meridian/` directory here lands exactly there.
SUBDOMAIN_DIR = SITE / "meridian"
PAGE = SUBDOMAIN_DIR / "index.html"

#: Kept so the old /agent.html URL does not simply 404 for anyone who has it.
LEGACY_PAGE = SITE / "agent.html"
CANONICAL = "https://meridian.nikunjkaushik.com/"

NAV = """  <nav id="desktop-nav">
    <div class="logo"><a href="https://nikunjkaushik.com/index.html" style="text-decoration:none;color:inherit;">Nikunj Kaushik</a></div>
    <div>
      <ul class="nav-links">
        <li><a href="https://nikunjkaushik.com/index.html">Home</a></li>
        <li><a href="https://nikunjkaushik.com/projects.html">Projects</a></li>
        <li><a href="https://nikunjkaushik.com/blog.html">Blog</a></li>
        <li><a href="https://nikunjkaushik.com/ai-tools.html">AI Tools</a></li>
        <li><a href="https://nikunjkaushik.com/contact.html">Contact</a></li>
      </ul>
    </div>
  </nav>

  <nav id="hamburger-nav">
    <div class="logo"><a href="https://nikunjkaushik.com/index.html" style="text-decoration:none;color:inherit;">Nikunj Kaushik</a></div>
    <div class="hamburger-menu">
      <div class="hamburger-icon" onclick="toggleMenu()"><span></span><span></span><span></span></div>
      <ul class="menu-links">
        <li><a href="https://nikunjkaushik.com/index.html" onclick="toggleMenu()">Home</a></li>
        <li><a href="https://nikunjkaushik.com/projects.html" onclick="toggleMenu()">Projects</a></li>
        <li><a href="https://nikunjkaushik.com/blog.html" onclick="toggleMenu()">Blog</a></li>
        <li><a href="https://nikunjkaushik.com/ai-tools.html" onclick="toggleMenu()">AI Tools</a></li>
        <li><a href="https://nikunjkaushik.com/contact.html" onclick="toggleMenu()">Contact</a></li>
      </ul>
    </div>
  </nav>
"""


#: An armillary sphere. Every coordinate is computed once at build time, so the
#: page ships as plain SVG with no script and no image asset. Layers, outside in:
#: a reticle, a graduated bezel, a counter-turning inner scale, the sphere in
#: three pencil passes, two sets of graticules turning opposite ways, latitude
#: circles, an inclined ecliptic that librates, two nodes on separate orbits, a
#: radar ping, a sight-line with a trail, and a core that breathes.
FIGURE = """
    <div class="mx-figure">
      <svg id="meridian-fig" viewBox="0 0 400 400" role="img"
           aria-label="An armillary sphere: a graduated ring with turning graticules, an inclined ecliptic and two orbiting nodes">
        <defs>
          <filter id="mx-rough" x="-16%" y="-16%" width="132%" height="132%">
            <feTurbulence type="fractalNoise" baseFrequency="0.015" numOctaves="2"
                          seed="9" result="n"/>
            <feDisplacementMap in="SourceGraphic" in2="n" scale="2"/>
          </filter>
          <radialGradient id="mx-glow">
            <stop offset="0%" stop-color="var(--accent)" stop-opacity=".75"/>
            <stop offset="55%" stop-color="var(--accent)" stop-opacity=".14"/>
            <stop offset="100%" stop-color="var(--accent)" stop-opacity="0"/>
          </radialGradient>
          <radialGradient id="mx-node">
            <stop offset="0%" stop-color="var(--accent)" stop-opacity="1"/>
            <stop offset="100%" stop-color="var(--accent)" stop-opacity="0"/>
          </radialGradient>
          <linearGradient id="mx-trailg" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%"  stop-color="var(--accent)" stop-opacity="0"/>
            <stop offset="100%" stop-color="var(--accent)" stop-opacity=".30"/>
          </linearGradient>
        </defs>

        <g class="mx-stars">
          <circle class="mx-star bright" style="--sd:0.00s" cx="408.8" cy="52.4" r="1.07"/>
          <circle class="mx-star" style="--sd:0.55s" cx="9.4" cy="56.7" r="1.20"/>
          <circle class="mx-star" style="--sd:1.10s" cx="57.1" cy="-7.6" r="1.79"/>
          <circle class="mx-star" style="--sd:1.65s" cx="-43.6" cy="314.3" r="0.78"/>
          <circle class="mx-star" style="--sd:2.20s" cx="265.9" cy="418.4" r="1.18"/>
          <circle class="mx-star" style="--sd:2.75s" cx="-9.3" cy="321.6" r="0.96"/>
          <circle class="mx-star" style="--sd:3.30s" cx="203.3" cy="441.3" r="0.99"/>
          <circle class="mx-star" style="--sd:3.85s" cx="5.1" cy="330.2" r="0.64"/>
          <circle class="mx-star" style="--sd:4.40s" cx="45.4" cy="27.7" r="1.30"/>
          <circle class="mx-star bright" style="--sd:4.95s" cx="278.8" cy="-52.0" r="1.72"/>
          <circle class="mx-star" style="--sd:5.50s" cx="-2.5" cy="97.8" r="1.77"/>
          <circle class="mx-star" style="--sd:0.00s" cx="306.4" cy="14.8" r="0.92"/>
          <circle class="mx-star" style="--sd:0.55s" cx="341.2" cy="33.7" r="1.42"/>
          <circle class="mx-star" style="--sd:1.10s" cx="413.8" cy="32.1" r="1.68"/>
          <circle class="mx-star" style="--sd:1.65s" cx="277.4" cy="412.1" r="0.85"/>
          <circle class="mx-star" style="--sd:2.20s" cx="445.9" cy="294.9" r="1.61"/>
          <circle class="mx-star" style="--sd:2.75s" cx="201.2" cy="431.2" r="1.10"/>
          <circle class="mx-star" style="--sd:3.30s" cx="120.9" cy="-56.0" r="1.34"/>
          <circle class="mx-star bright" style="--sd:3.85s" cx="-3.4" cy="62.6" r="0.79"/>
          <circle class="mx-star" style="--sd:4.40s" cx="457.3" cy="262.0" r="1.21"/>
          <circle class="mx-star" style="--sd:4.95s" cx="110.6" cy="422.7" r="0.79"/>
          <circle class="mx-star" style="--sd:5.50s" cx="409.5" cy="104.1" r="1.72"/>
          <circle class="mx-star" style="--sd:0.00s" cx="117.0" cy="-12.2" r="0.59"/>
          <circle class="mx-star" style="--sd:0.55s" cx="418.9" cy="322.5" r="1.58"/>
          <circle class="mx-star" style="--sd:1.10s" cx="435.6" cy="129.2" r="0.65"/>
          <circle class="mx-star" style="--sd:1.65s" cx="-26.9" cy="204.4" r="1.31"/>
          <circle class="mx-star" style="--sd:2.20s" cx="394.8" cy="106.0" r="1.37"/>
          <circle class="mx-star bright" style="--sd:2.75s" cx="367.7" cy="395.2" r="1.01"/>
          <circle class="mx-star" style="--sd:3.30s" cx="-23.3" cy="181.8" r="0.88"/>
          <circle class="mx-star" style="--sd:3.85s" cx="124.4" cy="393.8" r="0.64"/>
          <circle class="mx-star" style="--sd:4.40s" cx="223.2" cy="-24.5" r="0.67"/>
          <circle class="mx-star" style="--sd:4.95s" cx="433.4" cy="207.5" r="1.33"/>
          <circle class="mx-star" style="--sd:5.50s" cx="355.3" cy="357.1" r="1.06"/>
          <circle class="mx-star" style="--sd:0.00s" cx="-6.5" cy="176.3" r="0.87"/>
          <circle class="mx-star" style="--sd:0.55s" cx="309.8" cy="-31.2" r="1.23"/>
          <circle class="mx-star" style="--sd:1.10s" cx="-12.1" cy="365.2" r="1.74"/>
          <circle class="mx-star bright" style="--sd:1.65s" cx="-40.0" cy="249.5" r="0.97"/>
          <circle class="mx-star" style="--sd:2.20s" cx="369.0" cy="-1.1" r="1.65"/>
          <circle class="mx-star" style="--sd:2.75s" cx="-49.5" cy="277.0" r="1.67"/>
          <circle class="mx-star" style="--sd:3.30s" cx="229.0" cy="425.7" r="1.44"/>
          <circle class="mx-star" style="--sd:3.85s" cx="-2.4" cy="376.2" r="1.80"/>
          <circle class="mx-star" style="--sd:4.40s" cx="160.0" cy="441.3" r="1.01"/>
          <circle class="mx-star" style="--sd:4.95s" cx="417.1" cy="321.8" r="1.03"/>
          <circle class="mx-star" style="--sd:5.50s" cx="378.5" cy="344.4" r="1.34"/>
        </g>
        <g class="mx-reticle">
          <path class="mx-bracket" d="M20 4 L4 4 L4 20"/>
          <path class="mx-bracket" d="M380 4 L396 4 L396 20"/>
          <path class="mx-bracket" d="M20 396 L4 396 L4 380"/>
          <path class="mx-bracket" d="M380 396 L396 396 L396 380"/>
        </g>

        <g class="mx-instrument" filter="url(#mx-rough)">
          <g class="mx-bezel">
            <line class="mx-tick major" x1="200.0" y1="4.0" x2="200.0" y2="16.0"/>
            <line class="mx-tick" x1="212.8" y1="4.4" x2="212.5" y2="9.4"/>
            <line class="mx-tick" x1="225.6" y1="5.7" x2="224.9" y2="10.6"/>
            <line class="mx-tick" x1="238.2" y1="7.8" x2="237.3" y2="12.7"/>
            <line class="mx-tick" x1="250.7" y1="10.7" x2="249.4" y2="15.5"/>
            <line class="mx-tick" x1="263.0" y1="14.4" x2="261.4" y2="19.1"/>
            <line class="mx-tick" x1="275.0" y1="18.9" x2="273.1" y2="23.5"/>
            <line class="mx-tick" x1="286.7" y1="24.2" x2="284.5" y2="28.7"/>
            <line class="mx-tick major" x1="298.0" y1="30.3" x2="292.0" y2="40.7"/>
            <line class="mx-tick" x1="308.9" y1="37.0" x2="306.1" y2="41.2"/>
            <line class="mx-tick" x1="319.3" y1="44.5" x2="316.3" y2="48.5"/>
            <line class="mx-tick" x1="329.2" y1="52.6" x2="325.9" y2="56.4"/>
            <line class="mx-tick" x1="338.6" y1="61.4" x2="335.1" y2="64.9"/>
            <line class="mx-tick" x1="347.4" y1="70.8" x2="343.6" y2="74.1"/>
            <line class="mx-tick" x1="355.5" y1="80.7" x2="351.5" y2="83.7"/>
            <line class="mx-tick" x1="363.0" y1="91.1" x2="358.8" y2="93.9"/>
            <line class="mx-tick major" x1="369.7" y1="102.0" x2="359.3" y2="108.0"/>
            <line class="mx-tick" x1="375.8" y1="113.3" x2="371.3" y2="115.5"/>
            <line class="mx-tick" x1="381.1" y1="125.0" x2="376.5" y2="126.9"/>
            <line class="mx-tick" x1="385.6" y1="137.0" x2="380.9" y2="138.6"/>
            <line class="mx-tick" x1="389.3" y1="149.3" x2="384.5" y2="150.6"/>
            <line class="mx-tick" x1="392.2" y1="161.8" x2="387.3" y2="162.7"/>
            <line class="mx-tick" x1="394.3" y1="174.4" x2="389.4" y2="175.1"/>
            <line class="mx-tick" x1="395.6" y1="187.2" x2="390.6" y2="187.5"/>
            <line class="mx-tick major" x1="396.0" y1="200.0" x2="384.0" y2="200.0"/>
            <line class="mx-tick" x1="395.6" y1="212.8" x2="390.6" y2="212.5"/>
            <line class="mx-tick" x1="394.3" y1="225.6" x2="389.4" y2="224.9"/>
            <line class="mx-tick" x1="392.2" y1="238.2" x2="387.3" y2="237.3"/>
            <line class="mx-tick" x1="389.3" y1="250.7" x2="384.5" y2="249.4"/>
            <line class="mx-tick" x1="385.6" y1="263.0" x2="380.9" y2="261.4"/>
            <line class="mx-tick" x1="381.1" y1="275.0" x2="376.5" y2="273.1"/>
            <line class="mx-tick" x1="375.8" y1="286.7" x2="371.3" y2="284.5"/>
            <line class="mx-tick major" x1="369.7" y1="298.0" x2="359.3" y2="292.0"/>
            <line class="mx-tick" x1="363.0" y1="308.9" x2="358.8" y2="306.1"/>
            <line class="mx-tick" x1="355.5" y1="319.3" x2="351.5" y2="316.3"/>
            <line class="mx-tick" x1="347.4" y1="329.2" x2="343.6" y2="325.9"/>
            <line class="mx-tick" x1="338.6" y1="338.6" x2="335.1" y2="335.1"/>
            <line class="mx-tick" x1="329.2" y1="347.4" x2="325.9" y2="343.6"/>
            <line class="mx-tick" x1="319.3" y1="355.5" x2="316.3" y2="351.5"/>
            <line class="mx-tick" x1="308.9" y1="363.0" x2="306.1" y2="358.8"/>
            <line class="mx-tick major" x1="298.0" y1="369.7" x2="292.0" y2="359.3"/>
            <line class="mx-tick" x1="286.7" y1="375.8" x2="284.5" y2="371.3"/>
            <line class="mx-tick" x1="275.0" y1="381.1" x2="273.1" y2="376.5"/>
            <line class="mx-tick" x1="263.0" y1="385.6" x2="261.4" y2="380.9"/>
            <line class="mx-tick" x1="250.7" y1="389.3" x2="249.4" y2="384.5"/>
            <line class="mx-tick" x1="238.2" y1="392.2" x2="237.3" y2="387.3"/>
            <line class="mx-tick" x1="225.6" y1="394.3" x2="224.9" y2="389.4"/>
            <line class="mx-tick" x1="212.8" y1="395.6" x2="212.5" y2="390.6"/>
            <line class="mx-tick major" x1="200.0" y1="396.0" x2="200.0" y2="384.0"/>
            <line class="mx-tick" x1="187.2" y1="395.6" x2="187.5" y2="390.6"/>
            <line class="mx-tick" x1="174.4" y1="394.3" x2="175.1" y2="389.4"/>
            <line class="mx-tick" x1="161.8" y1="392.2" x2="162.7" y2="387.3"/>
            <line class="mx-tick" x1="149.3" y1="389.3" x2="150.6" y2="384.5"/>
            <line class="mx-tick" x1="137.0" y1="385.6" x2="138.6" y2="380.9"/>
            <line class="mx-tick" x1="125.0" y1="381.1" x2="126.9" y2="376.5"/>
            <line class="mx-tick" x1="113.3" y1="375.8" x2="115.5" y2="371.3"/>
            <line class="mx-tick major" x1="102.0" y1="369.7" x2="108.0" y2="359.3"/>
            <line class="mx-tick" x1="91.1" y1="363.0" x2="93.9" y2="358.8"/>
            <line class="mx-tick" x1="80.7" y1="355.5" x2="83.7" y2="351.5"/>
            <line class="mx-tick" x1="70.8" y1="347.4" x2="74.1" y2="343.6"/>
            <line class="mx-tick" x1="61.4" y1="338.6" x2="64.9" y2="335.1"/>
            <line class="mx-tick" x1="52.6" y1="329.2" x2="56.4" y2="325.9"/>
            <line class="mx-tick" x1="44.5" y1="319.3" x2="48.5" y2="316.3"/>
            <line class="mx-tick" x1="37.0" y1="308.9" x2="41.2" y2="306.1"/>
            <line class="mx-tick major" x1="30.3" y1="298.0" x2="40.7" y2="292.0"/>
            <line class="mx-tick" x1="24.2" y1="286.7" x2="28.7" y2="284.5"/>
            <line class="mx-tick" x1="18.9" y1="275.0" x2="23.5" y2="273.1"/>
            <line class="mx-tick" x1="14.4" y1="263.0" x2="19.1" y2="261.4"/>
            <line class="mx-tick" x1="10.7" y1="250.7" x2="15.5" y2="249.4"/>
            <line class="mx-tick" x1="7.8" y1="238.2" x2="12.7" y2="237.3"/>
            <line class="mx-tick" x1="5.7" y1="225.6" x2="10.6" y2="224.9"/>
            <line class="mx-tick" x1="4.4" y1="212.8" x2="9.4" y2="212.5"/>
            <line class="mx-tick major" x1="4.0" y1="200.0" x2="16.0" y2="200.0"/>
            <line class="mx-tick" x1="4.4" y1="187.2" x2="9.4" y2="187.5"/>
            <line class="mx-tick" x1="5.7" y1="174.4" x2="10.6" y2="175.1"/>
            <line class="mx-tick" x1="7.8" y1="161.8" x2="12.7" y2="162.7"/>
            <line class="mx-tick" x1="10.7" y1="149.3" x2="15.5" y2="150.6"/>
            <line class="mx-tick" x1="14.4" y1="137.0" x2="19.1" y2="138.6"/>
            <line class="mx-tick" x1="18.9" y1="125.0" x2="23.5" y2="126.9"/>
            <line class="mx-tick" x1="24.2" y1="113.3" x2="28.7" y2="115.5"/>
            <line class="mx-tick major" x1="30.3" y1="102.0" x2="40.7" y2="108.0"/>
            <line class="mx-tick" x1="37.0" y1="91.1" x2="41.2" y2="93.9"/>
            <line class="mx-tick" x1="44.5" y1="80.7" x2="48.5" y2="83.7"/>
            <line class="mx-tick" x1="52.6" y1="70.8" x2="56.4" y2="74.1"/>
            <line class="mx-tick" x1="61.4" y1="61.4" x2="64.9" y2="64.9"/>
            <line class="mx-tick" x1="70.8" y1="52.6" x2="74.1" y2="56.4"/>
            <line class="mx-tick" x1="80.7" y1="44.5" x2="83.7" y2="48.5"/>
            <line class="mx-tick" x1="91.1" y1="37.0" x2="93.9" y2="41.2"/>
            <line class="mx-tick major" x1="102.0" y1="30.3" x2="108.0" y2="40.7"/>
            <line class="mx-tick" x1="113.3" y1="24.2" x2="115.5" y2="28.7"/>
            <line class="mx-tick" x1="125.0" y1="18.9" x2="126.9" y2="23.5"/>
            <line class="mx-tick" x1="137.0" y1="14.4" x2="138.6" y2="19.1"/>
            <line class="mx-tick" x1="149.3" y1="10.7" x2="150.6" y2="15.5"/>
            <line class="mx-tick" x1="161.8" y1="7.8" x2="162.7" y2="12.7"/>
            <line class="mx-tick" x1="174.4" y1="5.7" x2="175.1" y2="10.6"/>
            <line class="mx-tick" x1="187.2" y1="4.4" x2="187.5" y2="9.4"/>
          </g>
          <circle class="mx-ink mx-thin" cx="200" cy="200" r="182"/>
          <circle class="mx-ink mx-faint mx-dot" cx="200" cy="200" r="174"/>

          <g class="mx-bezel-in">
            <line class="mx-tick in major" x1="200.0" y1="34.0" x2="200.0" y2="43.0"/>
            <line class="mx-tick in" x1="221.7" y1="35.4" x2="221.1" y2="39.4"/>
            <line class="mx-tick in" x1="243.0" y1="39.7" x2="241.9" y2="43.5"/>
            <line class="mx-tick in" x1="263.5" y1="46.6" x2="262.0" y2="50.3"/>
            <line class="mx-tick in major" x1="283.0" y1="56.2" x2="278.5" y2="64.0"/>
            <line class="mx-tick in" x1="301.1" y1="68.3" x2="298.6" y2="71.5"/>
            <line class="mx-tick in" x1="317.4" y1="82.6" x2="314.6" y2="85.4"/>
            <line class="mx-tick in" x1="331.7" y1="98.9" x2="328.5" y2="101.4"/>
            <line class="mx-tick in major" x1="343.8" y1="117.0" x2="336.0" y2="121.5"/>
            <line class="mx-tick in" x1="353.4" y1="136.5" x2="349.7" y2="138.0"/>
            <line class="mx-tick in" x1="360.3" y1="157.0" x2="356.5" y2="158.1"/>
            <line class="mx-tick in" x1="364.6" y1="178.3" x2="360.6" y2="178.9"/>
            <line class="mx-tick in major" x1="366.0" y1="200.0" x2="357.0" y2="200.0"/>
            <line class="mx-tick in" x1="364.6" y1="221.7" x2="360.6" y2="221.1"/>
            <line class="mx-tick in" x1="360.3" y1="243.0" x2="356.5" y2="241.9"/>
            <line class="mx-tick in" x1="353.4" y1="263.5" x2="349.7" y2="262.0"/>
            <line class="mx-tick in major" x1="343.8" y1="283.0" x2="336.0" y2="278.5"/>
            <line class="mx-tick in" x1="331.7" y1="301.1" x2="328.5" y2="298.6"/>
            <line class="mx-tick in" x1="317.4" y1="317.4" x2="314.6" y2="314.6"/>
            <line class="mx-tick in" x1="301.1" y1="331.7" x2="298.6" y2="328.5"/>
            <line class="mx-tick in major" x1="283.0" y1="343.8" x2="278.5" y2="336.0"/>
            <line class="mx-tick in" x1="263.5" y1="353.4" x2="262.0" y2="349.7"/>
            <line class="mx-tick in" x1="243.0" y1="360.3" x2="241.9" y2="356.5"/>
            <line class="mx-tick in" x1="221.7" y1="364.6" x2="221.1" y2="360.6"/>
            <line class="mx-tick in major" x1="200.0" y1="366.0" x2="200.0" y2="357.0"/>
            <line class="mx-tick in" x1="178.3" y1="364.6" x2="178.9" y2="360.6"/>
            <line class="mx-tick in" x1="157.0" y1="360.3" x2="158.1" y2="356.5"/>
            <line class="mx-tick in" x1="136.5" y1="353.4" x2="138.0" y2="349.7"/>
            <line class="mx-tick in major" x1="117.0" y1="343.8" x2="121.5" y2="336.0"/>
            <line class="mx-tick in" x1="98.9" y1="331.7" x2="101.4" y2="328.5"/>
            <line class="mx-tick in" x1="82.6" y1="317.4" x2="85.4" y2="314.6"/>
            <line class="mx-tick in" x1="68.3" y1="301.1" x2="71.5" y2="298.6"/>
            <line class="mx-tick in major" x1="56.2" y1="283.0" x2="64.0" y2="278.5"/>
            <line class="mx-tick in" x1="46.6" y1="263.5" x2="50.3" y2="262.0"/>
            <line class="mx-tick in" x1="39.7" y1="243.0" x2="43.5" y2="241.9"/>
            <line class="mx-tick in" x1="35.4" y1="221.7" x2="39.4" y2="221.1"/>
            <line class="mx-tick in major" x1="34.0" y1="200.0" x2="43.0" y2="200.0"/>
            <line class="mx-tick in" x1="35.4" y1="178.3" x2="39.4" y2="178.9"/>
            <line class="mx-tick in" x1="39.7" y1="157.0" x2="43.5" y2="158.1"/>
            <line class="mx-tick in" x1="46.6" y1="136.5" x2="50.3" y2="138.0"/>
            <line class="mx-tick in major" x1="56.2" y1="117.0" x2="64.0" y2="121.5"/>
            <line class="mx-tick in" x1="68.3" y1="98.9" x2="71.5" y2="101.4"/>
            <line class="mx-tick in" x1="82.6" y1="82.6" x2="85.4" y2="85.4"/>
            <line class="mx-tick in" x1="98.9" y1="68.3" x2="101.4" y2="71.5"/>
            <line class="mx-tick in major" x1="117.0" y1="56.2" x2="121.5" y2="64.0"/>
            <line class="mx-tick in" x1="136.5" y1="46.6" x2="138.0" y2="50.3"/>
            <line class="mx-tick in" x1="157.0" y1="39.7" x2="158.1" y2="43.5"/>
            <line class="mx-tick in" x1="178.3" y1="35.4" x2="178.9" y2="39.4"/>
            <line class="mx-spoke" x1="352.0" y1="200.0" x2="368.0" y2="200.0"/>
            <line class="mx-spoke" x1="331.6" y1="276.0" x2="345.5" y2="284.0"/>
            <line class="mx-spoke" x1="276.0" y1="331.6" x2="284.0" y2="345.5"/>
            <line class="mx-spoke" x1="200.0" y1="352.0" x2="200.0" y2="368.0"/>
            <line class="mx-spoke" x1="124.0" y1="331.6" x2="116.0" y2="345.5"/>
            <line class="mx-spoke" x1="68.4" y1="276.0" x2="54.5" y2="284.0"/>
            <line class="mx-spoke" x1="48.0" y1="200.0" x2="32.0" y2="200.0"/>
            <line class="mx-spoke" x1="68.4" y1="124.0" x2="54.5" y2="116.0"/>
            <line class="mx-spoke" x1="124.0" y1="68.4" x2="116.0" y2="54.5"/>
            <line class="mx-spoke" x1="200.0" y1="48.0" x2="200.0" y2="32.0"/>
            <line class="mx-spoke" x1="276.0" y1="68.4" x2="284.0" y2="54.5"/>
            <line class="mx-spoke" x1="331.6" y1="124.0" x2="345.5" y2="116.0"/>
          </g>
          <circle class="mx-ink mx-thin" cx="200" cy="200" r="152"/>

          <circle class="mx-ink mx-draw" style="--d:.0s"  cx="200" cy="200" r="138"/>
          <circle class="mx-ink mx-thin mx-draw" style="--d:.2s" cx="201" cy="199" r="142"/>
          <circle class="mx-ink mx-thin mx-draw" style="--d:.38s" cx="199" cy="201" r="133"/>

          <g class="mx-turn-a">
            <ellipse class="mx-ink mx-thin" cx="200" cy="200" rx="40"  ry="138"/>
            <ellipse class="mx-ink mx-thin" cx="200" cy="200" rx="84"  ry="138"/>
            <ellipse class="mx-ink mx-faint" cx="200" cy="200" rx="118" ry="138"/>
            <line    class="mx-ink mx-thin" x1="200" y1="62" x2="200" y2="338"/>
          </g>
          <g class="mx-turn-b">
            <ellipse class="mx-ink mx-faint" cx="200" cy="200" rx="62"  ry="138"/>
            <ellipse class="mx-ink mx-faint" cx="200" cy="200" rx="104" ry="138"/>
          </g>

          <ellipse class="mx-ink mx-faint" cx="200" cy="200" rx="138" ry="34"/>
          <ellipse class="mx-ink mx-faint" cx="200" cy="200" rx="131" ry="72"/>
          <ellipse class="mx-ink mx-faint" cx="200" cy="200" rx="110" ry="108"/>
          <line class="mx-ink mx-draw" style="--d:.55s" x1="62" y1="200" x2="338" y2="200"/>

          <g class="mx-ecliptic">
            <ellipse class="mx-ink mx-ecl" cx="200" cy="200" rx="156" ry="50"/>
          </g>

          <circle class="mx-ping" cx="200" cy="200" r="24"/>
          <circle class="mx-ping late" cx="200" cy="200" r="24"/>

          <g class="mx-orbit">
            <circle class="mx-nodehalo" cx="200" cy="62" r="12" fill="url(#mx-node)"/>
            <circle class="mx-nodecore" cx="200" cy="62" r="3.2"/>
          </g>
          <g class="mx-orbit2">
            <circle class="mx-nodecore sm" cx="200" cy="296" r="2.2"/>
          </g>

          <g class="mx-sweep">
            <path class="mx-trail" d="M200 200 L172 70 A138 138 0 0 1 228 70 Z"
                  fill="url(#mx-trailg)"/>
            <line class="mx-sight" x1="200" y1="200" x2="200" y2="64"/>
          </g>
        </g>

        <circle class="mx-halo" cx="200" cy="200" r="42" fill="url(#mx-glow)"/>
        <circle class="mx-core" cx="200" cy="200" r="5"/>
      </svg>
      <p class="mx-figcap">Meridian &mdash; awake, and looking.</p>
    </div>
"""

CSS = """
  :root { --accent:#4A6FA5; --ink:#111; --ink-2:#585858; --muted:#8a8a8a;
          --line:rgba(190,195,205,.55); --bg:#fff; }
  @media (prefers-color-scheme: dark) {
    :root { --accent:#7fa3d8; --ink:#e8eaee; --ink-2:#a4a8b1; --muted:#7f8694;
            --line:rgba(255,255,255,.12); --bg:#0b0d11; }
  }
  * { box-sizing:border-box; }
  html, body { height:100%; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font-family:"Poppins",system-ui,-apple-system,sans-serif;
         line-height:1.6; -webkit-font-smoothing:antialiased;
         display:flex; flex-direction:column; min-height:100vh; min-height:100dvh; }
  body::before { content:''; position:fixed; inset:0; z-index:-1; pointer-events:none;
    background:
      radial-gradient(760px circle at 20% 8%,  rgba(74,111,165,.20), transparent 62%),
      radial-gradient(680px circle at 84% 22%, rgba(123,104,238,.14), transparent 60%),
      radial-gradient(820px circle at 70% 92%, rgba(240,160,90,.10), transparent 62%); }
  a { color:var(--accent); text-decoration:none; }
  a:hover { text-decoration:underline; }

  /* no navigation: this page stands on its own */

  /* the hero owns whatever height is left */
  main { flex:1; display:flex; flex-direction:column; align-items:center;
         justify-content:center; text-align:center; width:100%;
         padding:2.5rem 1.6rem; }
  .mx-eyebrow { font-size:.76rem; font-weight:500; letter-spacing:.14em;
                text-transform:uppercase; color:var(--accent); margin:0 0 .4rem; }
  .mx-title { font-size:clamp(2.6rem, 7vw, 4.4rem); font-weight:600;
              letter-spacing:-.025em; margin:0; line-height:1.05; }
  .mx-intro { color:var(--ink-2); line-height:1.8; font-size:clamp(.92rem,1.6vw,1.02rem);
              max-width:40rem; margin:.4rem auto 0; }

  /* ---- the instrument ---- */
  .mx-figure { display:flex; flex-direction:column; align-items:center;
               margin:.6rem auto 1.4rem; }
  .mx-figure svg { width:clamp(230px, 34vh, 400px); height:auto; overflow:visible;
                   color:var(--ink); }
  .mx-ink { fill:none; stroke:currentColor; stroke-width:1.5;
            stroke-linecap:round; opacity:.5; }
  .mx-thin  { stroke-width:.85; opacity:.28; }
  .mx-faint { stroke-width:.7;  opacity:.16; }
  .mx-tick { stroke:currentColor; stroke-width:.75; opacity:.18; }
  .mx-tick.major { stroke-width:1.25; opacity:.38; }
  .mx-tick.in { stroke-width:.65; opacity:.13; }
  .mx-tick.in.major { stroke-width:1; opacity:.26; }
  .mx-spoke { stroke:currentColor; stroke-width:.7; opacity:.14; }
  .mx-dot { stroke-dasharray:1.5 6; }
  .mx-bracket { fill:none; stroke:var(--accent); stroke-width:1.3; opacity:.3;
                stroke-linecap:round; }
  .mx-ping { fill:none; stroke:var(--accent); stroke-width:1.1;
             transform-origin:200px 200px; opacity:0;
             animation:mx-ping 7s cubic-bezier(.2,.6,.3,1) infinite; }
  .mx-ping.late { animation-delay:3.5s; }
  .mx-trail { opacity:.75; }
  .mx-nodecore.sm { opacity:.6; }
  .mx-star.bright { opacity:.34; }
  .mx-ecl { stroke:var(--accent); stroke-width:1.1; opacity:.4;
            stroke-dasharray:5 7; }
  .mx-sight { stroke:var(--accent); stroke-width:1.2; opacity:.45; }
  .mx-core { fill:var(--accent); }
  .mx-nodecore { fill:var(--accent); }
  .mx-star { fill:currentColor; opacity:.18;
             animation:mx-twinkle 5s ease-in-out infinite; animation-delay:var(--sd,0s); }
  .mx-figcap { font-size:.72rem; letter-spacing:.14em; text-transform:uppercase;
               color:var(--muted); margin:1.1rem 0 0; }

  .mx-draw { stroke-dasharray:1200; stroke-dashoffset:1200;
             animation:mx-ink-in 2.4s cubic-bezier(.3,.8,.3,1) forwards;
             animation-delay:var(--d,0s); }
  @keyframes mx-ink-in { to { stroke-dashoffset:0; } }

  .mx-bezel    { transform-origin:200px 200px; animation:mx-spin 240s linear infinite; }
  .mx-bezel-in { transform-origin:200px 200px; animation:mx-spin 150s linear infinite reverse; }
  .mx-reticle  { transform-origin:200px 200px; animation:mx-breathe 9s ease-in-out infinite; }
  .mx-orbit2   { transform-origin:200px 200px; animation:mx-spin 34s linear infinite reverse; }
  .mx-turn-a   { transform-origin:200px 200px; animation:mx-spin 64s linear infinite; }
  .mx-turn-b   { transform-origin:200px 200px; animation:mx-spin 96s linear infinite reverse; }
  .mx-ecliptic { transform-origin:200px 200px; animation:mx-tilt 38s ease-in-out infinite; }
  .mx-orbit    { transform-origin:200px 200px; animation:mx-spin 22s linear infinite; }
  @keyframes mx-spin { to { transform:rotate(360deg); } }
  @keyframes mx-tilt {
    0%,100% { transform:rotate(-24deg) } 50% { transform:rotate(24deg) }
  }

  .mx-sweep { transform-origin:200px 200px;
              animation:mx-sweep 13s cubic-bezier(.45,0,.55,1) infinite; }
  @keyframes mx-sweep {
    0%,7%   { transform:rotate(-38deg) }
    50%,57% { transform:rotate(38deg)  }
    100%    { transform:rotate(-38deg) }
  }
  .mx-core, .mx-halo { transform-origin:200px 200px;
                       animation:mx-breathe 5s ease-in-out infinite; }
  .mx-nodehalo { animation:mx-breathe 2.6s ease-in-out infinite; }
  @keyframes mx-breathe {
    0%,100% { opacity:.95; transform:scale(1) }
    50%     { opacity:.5;  transform:scale(1.22) }
  }
  @keyframes mx-twinkle { 0%,100% { opacity:.08 } 50% { opacity:.3 } }
  @keyframes mx-ping {
    0%   { transform:scale(1);   opacity:0 }
    12%  { opacity:.45 }
    70%, 100% { transform:scale(6.4); opacity:0 }
  }

  @media (prefers-reduced-motion: reduce) {
    .mx-draw,.mx-bezel,.mx-bezel-in,.mx-turn-a,.mx-turn-b,.mx-ecliptic,
    .mx-orbit,.mx-orbit2,.mx-sweep,.mx-core,.mx-halo,.mx-nodehalo,
    .mx-star,.mx-ping,.mx-reticle { animation:none; }
    .mx-ping { opacity:0; }
    .mx-draw { stroke-dashoffset:0; }
  }
  @media (max-width:600px) { .mx-top { padding:1.1rem 1.1rem; } .mx-nav { gap:1.1rem; } }
"""



def _paras(text: str) -> str:
    """Model text to escaped paragraphs. Nothing survives that is not plain words."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text or "") if b.strip()]
    if not blocks:
        return ""
    return "\n".join(
        f"<p>{html.escape(re.sub(r'\\s+', ' ', b))}</p>" for b in blocks[:8]
    )


def _when(iso: str) -> str:
    try:
        d = dt.datetime.fromisoformat(iso)
    except ValueError:
        return iso[:16]
    return d.strftime("%d %b %Y, %H:%M UTC")


def render() -> str:
    # The page is a presence, not a feed: the journal lives in the database
    # and goes to Nikunj over Telegram. Nothing below the intro is rendered.


    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Meridian \u2014 an autonomous agent</title>
  <meta name="description" content="Meridian is an autonomous agent working for Nikunj Kaushik. It reads the open web, chooses what to look at and when to wake, and reports what it finds." />
  <link rel="canonical" href="{CANONICAL}" />
  <meta property="og:title" content="Meridian \u2014 an autonomous agent" />
  <meta property="og:description" content="An autonomous agent working for Nikunj Kaushik. It reads the open web and reports what it finds." />
  <meta property="og:url" content="{CANONICAL}" />
  <meta property="og:type" content="website" />
  <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
  <link rel="icon" href="/favicon-32.png" sizes="32x32" type="image/png" />
  <link rel="shortcut icon" href="/favicon.ico" />
  <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
  <meta name="theme-color" content="#0b0d11" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600&display=swap" rel="stylesheet" />
  <style>{CSS}</style>
</head>
<body>
  <main>
    <p class="mx-eyebrow">Built in the open</p>
    <h1 class="mx-title">Meridian</h1>
{FIGURE}
    <p class="mx-intro">Meridian is an autonomous agent. It works for Nikunj Kaushik.
      It reads the open web, keeps its own notes, and reports what it finds, choosing
      what to look at and when to wake.</p>

  </main>
</body>
</html>
"""


#: The footer carries a "last updated" time, which differs on every render. Comparing
#: it would make every cycle look like a change and push a commit every few minutes,
#: so it is normalised out before deciding whether anything actually moved.
_STAMP = re.compile(r"Last updated [^<.]*")


def _substance(page: str) -> str:
    return _STAMP.sub("Last updated —", page)


#: The old /agent.html URL is public and may be linked, so it redirects to the
#: subdomain rather than 404ing or serving a second copy. A copy would duplicate
#: content for search engines and would need its own favicon paths, since the two
#: live at different document roots.
REDIRECT = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Meridian</title>
  <link rel="canonical" href="{CANONICAL}" />
  <meta name="robots" content="noindex" />
  <meta http-equiv="refresh" content="0; url={CANONICAL}" />
</head>
<body>
  <p>Meridian has moved to <a href="{CANONICAL}">meridian.nikunjkaushik.com</a>.</p>
</body>
</html>
"""


def write() -> dict[str, object]:
    if not SITE.exists():
        return {"written": False, "reason": f"site repo not found at {SITE}"}
    changed: list[str] = []

    PAGE.parent.mkdir(parents=True, exist_ok=True)
    out = render()
    before = PAGE.read_text(encoding="utf-8") if PAGE.exists() else ""
    if _substance(before) != _substance(out):
        PAGE.write_text(out, encoding="utf-8")
        changed.append(str(PAGE.relative_to(SITE)))

    old = LEGACY_PAGE.read_text(encoding="utf-8") if LEGACY_PAGE.exists() else ""
    if old != REDIRECT:
        LEGACY_PAGE.write_text(REDIRECT, encoding="utf-8")
        changed.append(str(LEGACY_PAGE.relative_to(SITE)))

    if not changed:
        return {"written": False, "reason": "no new journal entries"}
    return {"written": True, "paths": changed, "bytes": len(out)}
