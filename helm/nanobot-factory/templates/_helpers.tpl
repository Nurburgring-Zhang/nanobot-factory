{{/*
Expand the name of the chart.
*/}}
{{- define "nanobot-factory.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "nanobot-factory.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Common labels + selector template.
Usage:
  {{ include "nanobot-factory.commonLabels" (dict "ctx" . "name" "user-service") }}
*/}}
{{- define "nanobot-factory.commonLabels" -}}
{{- $ctx := .ctx -}}
{{- $name := .name -}}
app.kubernetes.io/name: {{ $name | default $ctx.Chart.Name }}
app.kubernetes.io/instance: {{ $ctx.Release.Name }}
app.kubernetes.io/version: {{ $ctx.Chart.AppVersion | replace "+" "_" | quote }}
app.kubernetes.io/managed-by: {{ $ctx.Release.Service }}
app.kubernetes.io/part-of: nanobot-factory
helm.sh/chart: {{ printf "%s-%s" $ctx.Chart.Name $ctx.Chart.Version | replace "+" "_" }}
{{- end -}}

{{/*
Selector labels (must match template labels exactly).
*/}}
{{- define "nanobot-factory.selectorLabels" -}}
{{- $ctx := .ctx -}}
{{- $name := .name -}}
app.kubernetes.io/name: {{ $name }}
app.kubernetes.io/instance: {{ $ctx.Release.Name }}
{{- end -}}

{{/*
Image reference.
*/}}
{{- define "nanobot-factory.image" -}}
{{- $ctx := .ctx -}}
{{- printf "%s/%s:%s" $ctx.Values.image.registry $ctx.Values.image.repository $ctx.Values.image.tag -}}
{{- end -}}

{{/*
Resource limits - heavy vs default.
*/}}
{{- define "nanobot-factory.resources" -}}
{{- $ctx := .ctx -}}
{{- $heavy := .heavy | default false -}}
{{- if $heavy -}}
requests:
  cpu: {{ $ctx.Values.resources.requests.cpu }}
  memory: {{ $ctx.Values.resources.requests.memory }}
limits:
  cpu: {{ $ctx.Values.resources.heavy.cpu }}
  memory: {{ $ctx.Values.resources.heavy.memory }}
{{- else -}}
requests:
  cpu: {{ $ctx.Values.resources.requests.cpu }}
  memory: {{ $ctx.Values.resources.requests.memory }}
limits:
  cpu: {{ $ctx.Values.resources.limits.cpu }}
  memory: {{ $ctx.Values.resources.limits.memory }}
{{- end -}}
{{- end -}}