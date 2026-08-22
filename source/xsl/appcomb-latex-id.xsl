<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">
  <xsl:import href="./core/pretext-latex.xsl"/>

  <!-- Keep HTML and print exports on the same id-ID catalog. -->
  <xsl:variable name="locales"
                select="document('localizations/localizations.xml')/localizations/locale"/>
  <xsl:variable name="locale-files"
                select="document('localizations/localizations.xml')/localizations/filename"/>
  <xsl:variable name="localizations" select="document($locale-files)"/>

  <!--
    Two authority-source displays use raw TeX line breaks inside md.  Core
    PreTeXt places raw md in equation*, where those breaks do not reflow.
    Keep the authority topology unchanged and wrap only these two uniquely
    identified displays as aligned equations in the PDF/LaTeX output.
  -->
  <xsl:template match="md[contains(., 'P_{D_8}(w+g+b,w^2+g^2+b^2')]"><xsl:text>\begin{align*}
P_{D_8}(w+g+b,w^2+g^2+b^2,w^3+g^3+b^3,w^4+g^4+b^4) &amp;={}\\
&amp; b^4+b^3 g+2 b^2 g^2+b g^3+g^4\\
&amp; {}+b^3 w+2 b^2 g w+2 b g^2 w+g^3 w\\
&amp; {}+2 b^2 w^2+2 b g w^2+2 g^2 w^2+b w^3+g w^3+w^4.
\end{align*}</xsl:text></xsl:template>

  <xsl:template match="md[contains(., '1+h+3 h^2+3 h^3+3 h^4+h^5+h^6+m')]"><xsl:text>\begin{align*}
&amp; 1+h+3 h^2+3 h^3+3 h^4+h^5+h^6\\
&amp; {}+m+3 h m+6 h^2 m+6 h^3 m+3 h^4 m+h^5 m\\
&amp; {}+3 m^2+6 h m^2+11 h^2 m^2+6 h^3 m^2+3 h^4 m^2\\
&amp; {}+3 m^3+6 h m^3+6 h^2 m^3+3 h^3 m^3\\
&amp; {}+3 m^4+3 h m^4+3 h^2 m^4+m^5+h m^5+m^6.
\end{align*}</xsl:text></xsl:template>

  <!--
    The 89-digit Sage integer is one unbreakable listings token.  Preserve the
    exact PreTeXt input (and therefore HTML behavior), but print the same
    integer as three base-ten chunks in the PDF-only Sage surface.  The
    identity is exact: A*10^59 + B*10^29 + C equals the authority literal.
  -->
  <xsl:template match="sage[input = 'factor(55684901170770357082442831733350405217163692355899511509652043138898236817075547572153799)']">
    <xsl:apply-templates select="." mode="sage-active-markup">
      <xsl:with-param name="language-attribute" select="@language"/>
      <xsl:with-param name="b-autoeval" select="@auto-evaluate = 'yes'"/>
      <xsl:with-param name="in"><xsl:text>factor(
    556849011707703570824428317333 * 10^59
    + 504052171636923558995115096520 * 10^29
    + 43138898236817075547572153799
)</xsl:text></xsl:with-param>
      <xsl:with-param name="out" select="''"/>
    </xsl:apply-templates>
  </xsl:template>
</xsl:stylesheet>
