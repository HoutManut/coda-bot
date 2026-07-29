"""Translation boundary and read logic for the static song catalog.

The catalog ships as a bundled ``assets/arcsongs.json`` (an external/static shape);
:mod:`coda.catalog.dto` parses it into plain Python, :mod:`coda.catalog.seed`
upserts that into the ORM, and :mod:`coda.catalog.resolution` computes the
effective (inherited) field values for display. :mod:`coda.catalog.chart_resolution`
maps a wire ``(song_id, difficulty)`` score key to its ``song_difficulties`` row.
"""
