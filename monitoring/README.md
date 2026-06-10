# Monitoramento — CRM Gallo

Arquivos de observabilidade para o backend FastAPI.

## Métricas disponíveis

O backend expõe métricas Prometheus em `GET /metrics` via `PrometheusMiddleware` (`starlette-prometheus`).

Principais métricas:
| Métrica | Tipo | Descrição |
|---------|------|-----------|
| `starlette_requests_total` | Counter | Total de requests por método, path e status_code |
| `starlette_request_duration_seconds` | Histogram | Latência por método e path |
| `starlette_requests_in_progress` | Gauge | Requests em andamento no momento |

## Dashboard Grafana

**Arquivo:** `grafana-dashboard.json`

### Importar

1. Abra o Grafana → **Dashboards → Import**
2. Clique em **Upload JSON file** e selecione `grafana-dashboard.json`
3. Selecione o datasource Prometheus
4. Clique **Import**

### Painéis incluídos

| Painel | Descrição |
|--------|-----------|
| Request Rate | Req/s separado por 2xx / 4xx / 5xx |
| Error Rate % | Percentual de 5xx (alerta visual > 5%) |
| Latência p50/p95/p99 | Percentis de latência global |
| Slowest Endpoints | Top 10 endpoints com p95 > 500ms |
| Requests In-Flight | Gauge de requests simultâneos |
| Stats de erros | Contagem de 4xx e 5xx nos últimos 5 min |

## Alert Rules Prometheus

**Arquivo:** `alerts.yml`

### Configurar no Prometheus

Adicione ao `prometheus.yml`:

```yaml
rule_files:
  - /etc/prometheus/alerts.yml
```

Ou no Railway / Grafana Cloud, use o painel **Alerting → Alert rules → Import**.

### Alertas configurados

| Alerta | Condição | Severidade |
|--------|----------|------------|
| `HighErrorRate` | 5xx > 5% por 2 min | critical |
| `HighLatencyP95` | p95 > 1s por 5 min | warning |
| `NoInboundTraffic` | 0 requests por 10 min | warning |
| `OutboxDrainBacklog` | > 100 eventos pendentes por 5 min | warning |
| `High4xxRate` | 4xx > 20% por 3 min | warning |

> **Nota:** `OutboxDrainBacklog` requer a métrica `outbox_events_pending_total`.
> Adicione um endpoint Prometheus no worker que exponha essa contagem,
> ou use uma query direta no banco como fonte de dados.
