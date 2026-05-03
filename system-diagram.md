# System Architecture

## Runtime Flow

Three tiers. DuckDB/R2 handles all data reads; Snowflake Cortex handles `/ask` and prose until Phase 3.

```mermaid
flowchart TB
    subgraph BROWSER["BROWSER (SvelteKit)"]
        GEO[Geolocation / Places<br/>→ lat/lon → subregion_id]
        SCROLL[Scroll sections<br/>editorial data reveals]
        MAP[Google Maps JS API<br/>satellite · animated arc · eGRID overlay]
        H3UI[H3Density section<br/>hexbins + Cortex summary byline]
        CHAT[CortexChat<br/>chips · free-text · visible SQL]
        GEO --> SCROLL
    end

    subgraph API["CLOUD RUN (FastAPI, Python 3.12)"]
        MINE_EP[POST /mine-for-me<br/>→ mine + prose + stats]
        ASK_EP[POST /ask<br/>→ answer + SQL + rows]
        H3_EP[GET /h3-density<br/>→ hexbins + totals + summary]
        EMIT_EP[GET /emissions/{plant}<br/>→ CO₂ · SO₂ · NOₓ]
        DC[data_client.py<br/>DuckDB · httpfs · h3-py]
        FALLBACK[Fallback JSON<br/>19 subregions]
    end

    subgraph R2["CLOUDFLARE R2 · unearthed-data/"]
        MRT[(mrt/<br/>mine_plant_for_subregion.parquet<br/>emissions_by_plant.parquet<br/>v_mine_for_subregion.parquet)]
        RAW[(raw/<br/>msha_mines · msha_accidents<br/>eia_923 · eia_860 · lookup)]
    end

    subgraph SNOW["SNOWFLAKE (Phase 3 target: remove)"]
        CORTEX[Cortex Analyst<br/>semantic model YAML]
        COMPLETE[Cortex Complete<br/>llama3.3-70b prose]
        RO_EXEC[SQL Execution<br/>UNEARTHED_READONLY_ROLE]
    end

    SCROLL -->|POST subregion_id| MINE_EP
    CHAT -->|POST question| ASK_EP
    H3UI -->|GET| H3_EP
    SCROLL -->|GET /emissions/:plant| EMIT_EP

    MINE_EP --> DC
    H3_EP --> DC
    EMIT_EP --> DC
    DC --> MRT
    DC -.-> RAW

    MINE_EP -->|Snowflake down| FALLBACK
    MINE_EP -->|stats| COMPLETE
    COMPLETE -->|prose| MINE_EP

    ASK_EP -->|REST API| CORTEX
    CORTEX -->|SQL| RO_EXEC
    RO_EXEC -->|rows| ASK_EP

    style DC fill:#f6821f,color:#fff
    style MRT fill:#f6821f,color:#fff
    style RAW fill:#f6821f,color:#fff
    style CORTEX fill:#29b5e8,color:#fff
    style COMPLETE fill:#29b5e8,color:#fff
    style RO_EXEC fill:#29b5e8,color:#fff
    style FALLBACK fill:#6e6359,color:#fff
```

## Data Loading (one-time, repeat for refreshes)

```mermaid
flowchart LR
    MSHA1[MSHA Mines] --> EXP
    MSHA2[MSHA Quarterly Prod] --> EXP
    MSHA3[MSHA Accidents] --> EXP
    EIA1[EIA-923 Fuel Receipts] --> EXP
    EIA2[EIA-860 Plants] --> EXP
    MKT[EPA CAM<br/>Marketplace CTAS] --> EXP
    EXP["scripts/export_snowflake_to_parquet.py<br/>validates row counts against Snowflake"] --> LOCAL[local Parquet files]
    LOCAL --> UP["scripts/upload_to_r2.py<br/>idempotent boto3 upload"]
    UP --> R2[(R2 · unearthed-data/)]
    style R2 fill:#f6821f,color:#fff
```

## Security Layers

```mermaid
flowchart LR
    Q[User question] --> V{Pydantic validation<br/>regex + length}
    V -->|valid| CA[Cortex Analyst]
    V -->|invalid| R422[422 reject]
    CA -->|SQL| STRIP[Strip trailing<br/>semicolon]
    STRIP --> CHK{SQL validation<br/>SELECT only · no DML<br/>no remaining semicolons}
    CHK -->|safe| EXEC[Execute via<br/>READONLY_ROLE]
    CHK -->|unsafe| RVAL[ValueError reject]
    EXEC -->|500 rows max<br/>10s timeout| RESP[Response]
```

## DuckDB Connection Lifecycle

```mermaid
flowchart TB
    REQ[Incoming request] --> CHECK{_con initialized?}
    CHECK -->|yes| QUERY[execute parameterized query]
    CHECK -->|no| INIT[duckdb.connect ':memory:']
    INIT --> R2CHECK{R2_ACCESS_KEY_ID set?}
    R2CHECK -->|yes| HTTPFS[INSTALL httpfs · LOAD httpfs<br/>CREATE SECRET r2_data]
    R2CHECK -->|no| LOCAL[local file path via DATA_BASE_URL]
    HTTPFS --> QUERY
    LOCAL --> QUERY
    QUERY --> RETURN[return rows]
```
