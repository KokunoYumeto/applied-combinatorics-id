<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">
  <xsl:import href="./core/pretext-html.xsl"/>

  <!-- PreTeXt 2.49.1 does not ship id-ID.  Bind this derivative to the
       repository-local, source-controlled Indonesian localization catalog. -->
  <xsl:variable name="locales"
                select="document('localizations/localizations.xml')/localizations/locale"/>
  <xsl:variable name="locale-files"
                select="document('localizations/localizations.xml')/localizations/filename"/>
  <xsl:variable name="localizations" select="document($locale-files)"/>

  <!-- Keep the reading column centered and use the available page width.
       finalize-html-id.py installs this source-controlled stylesheet into the
       generated _static directory and verifies byte identity. -->
  <xsl:param name="html.css.extra" select="'_static/appcomb-id.css'"/>
</xsl:stylesheet>
