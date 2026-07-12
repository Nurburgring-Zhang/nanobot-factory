<template>
  <section class="billing-admin">
    <header class="admin-header">
      <h1>CDP Billing</h1>
      <p class="subtitle">
        V5 §13.4 / Chapter 22 — Advanced billing, multi-tier pricing &amp; invoicing.
      </p>
    </header>

    <n-grid :x-gap="16" :y-gap="16" cols="1 m:2 l:3" responsive="screen">
      <n-grid-item>
        <n-card title="Current Month Usage" hoverable>
          <div v-if="store.loading" data-testid="usage-loading">Loading...</div>
          <div v-else-if="!store.usage.length" data-testid="usage-empty" class="empty">
            No usage recorded yet.
          </div>
          <table v-else data-testid="usage-table" class="usage-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Qty</th>
                <th>Unit price</th>
                <th>Amount</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="line in store.usage" :key="line.metric">
                <td>{{ line.metric }} ({{ line.unit }})</td>
                <td>{{ line.qty }}</td>
                <td>${{ line.unit_price }}</td>
                <td>${{ line.amount.toFixed(2) }}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td colspan="3"><strong>Total</strong></td>
                <td><strong>${{ store.totalAmount.toFixed(2) }}</strong></td>
              </tr>
            </tfoot>
          </table>
        </n-card>
      </n-grid-item>

      <n-grid-item>
        <n-card title="Invoices" hoverable>
          <div v-if="store.loading" data-testid="invoices-loading">Loading...</div>
          <div v-else-if="!store.invoices.length" data-testid="invoices-empty" class="empty">
            No invoices yet.
          </div>
          <table v-else data-testid="invoices-table" class="invoices-table">
            <thead>
              <tr>
                <th>Period</th>
                <th>Total</th>
                <th>Tier</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="inv in store.invoices" :key="inv.id">
                <td>{{ inv.period_start }} → {{ inv.period_end }}</td>
                <td>${{ inv.total.toFixed(2) }}</td>
                <td>{{ inv.tier_applied || 'none' }}</td>
                <td>
                  <n-button
                    size="small"
                    type="primary"
                    :data-testid="`download-${inv.id}`"
                    @click="onDownload(inv.id)"
                  >
                    Download PDF
                  </n-button>
                </td>
              </tr>
            </tbody>
          </table>
        </n-card>
      </n-grid-item>

      <n-grid-item>
        <n-card title="Pricing Tiers" hoverable>
          <div v-if="store.loading" data-testid="tiers-loading">Loading...</div>
          <div v-else-if="!store.tiers.length" data-testid="tiers-empty" class="empty">
            No tiers configured.
          </div>
          <ol v-else data-testid="tiers-list" class="tiers-list">
            <li
              v-for="tier in store.tiers"
              :key="tier.name"
              :data-testid="`tier-${tier.name}`"
              class="tier-row"
            >
              <div class="tier-name">{{ tier.name }} <small>(≥ {{ tier.min_units.toLocaleString() }} units)</small></div>
              <div class="tier-discount">{{ tier.discount_pct }}% off</div>
              <div class="tier-desc">{{ tier.description }}</div>
            </li>
          </ol>
          <p v-if="store.currentTier" data-testid="current-tier" class="current-tier">
            Current tier: <strong>{{ store.currentTier.name }}</strong>
          </p>
        </n-card>
      </n-grid-item>
    </n-grid>
  </section>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { NButton, NCard, NGrid, NGridItem, createDiscreteApi } from 'naive-ui'
import { useBillingStore } from '@/stores/billing'

const store = useBillingStore()
// createDiscreteApi: works in jsdom without NMessageProvider wrapper (P19 v5.6 fix).
const { message } = createDiscreteApi(['message'])

onMounted(async () => {
  if (!store.loaded) await store.loadAll()
})

async function onDownload(invoiceId: string) {
  const result = await store.downloadInvoicePdf(invoiceId)
  message.success(`Invoice ${invoiceId} downloaded (${result.size} bytes, ${result.format.toUpperCase()})`)
}
</script>

<style scoped>
.billing-admin { padding: 16px 24px; max-width: 1280px; }
.admin-header { margin-bottom: 16px; }
.admin-header h1 { margin: 0 0 4px; font-size: 22px; font-weight: 600; }
.subtitle { color: #6b7280; font-size: 13px; margin: 0; }
.empty { padding: 24px; text-align: center; color: #6b7280; }

.usage-table, .invoices-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.usage-table th, .usage-table td,
.invoices-table th, .invoices-table td {
  padding: 6px 8px;
  border-bottom: 1px solid #e5e7eb;
  text-align: left;
}
.usage-table tfoot td,
.invoices-table tfoot td {
  border-top: 2px solid #d1d5db;
  border-bottom: none;
}

.tiers-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.tier-row {
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  margin-bottom: 8px;
}
.tier-name { font-weight: 600; font-size: 14px; }
.tier-name small { color: #6b7280; font-weight: 400; font-size: 12px; }
.tier-discount { color: #2563eb; font-size: 13px; margin: 2px 0; }
.tier-desc { color: #4b5563; font-size: 12px; }
.current-tier {
  margin-top: 16px;
  padding: 8px 12px;
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 6px;
  font-size: 13px;
}
</style>
