"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Download, FileText, LoaderCircle, Save, Sparkles, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useOllamaStatus } from "@/components/runtime-status";
import { MarkdownPreview } from "@/components/markdown-preview";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { downloadText } from "@/lib/download";
import type { ReadmeDraft } from "@/lib/types";

const ORIGIN_LABEL: Record<ReadmeDraft["origin"], string> = {
  deterministic: "Built from verified repository facts",
  deterministic_and_ai: "Verified facts, plus a labeled AI overview",
  edited: "Edited by you",
};

function Editor({ draft, id }: { draft: ReadmeDraft; id: string }) {
  const queryClient = useQueryClient();
  const [content, setContent] = useState(draft.content);
  const dirty = content !== draft.content;

  const save = useMutation({
    mutationFn: () => api.saveReadme(id, content),
    onSuccess: (saved) => {
      queryClient.setQueryData(["readme", id], saved);
      toast.success("Draft saved in GhostRepo. The repository was not changed.");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  async function copy() {
    try {
      await navigator.clipboard.writeText(content);
      toast.success("Copied to the clipboard.");
    } catch {
      toast.error("The browser blocked clipboard access.");
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <CardTitle>README draft</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">{ORIGIN_LABEL[draft.origin]}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => save.mutate()}
            disabled={!dirty || !content.trim() || save.isPending}
          >
            <Save aria-hidden />
            {save.isPending ? "Saving…" : "Save draft"}
          </Button>
          <Button size="sm" variant="outline" onClick={copy}>
            <Copy aria-hidden />
            Copy
          </Button>
          <Button size="sm" variant="outline" onClick={() => downloadText("README.md", content)}>
            <Download aria-hidden />
            Export
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {draft.warning && (
          <p
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-severity-high/40 bg-severity-high/10 p-3 text-sm"
          >
            <TriangleAlert className="mt-0.5 size-4 shrink-0 text-severity-high" aria-hidden />
            {draft.warning}
          </p>
        )}
        {draft.unverified_sections.length > 0 && (
          <p className="text-sm text-muted-foreground">
            Needs your confirmation: {draft.unverified_sections.join(", ")}.
          </p>
        )}
        <Tabs defaultValue="preview">
          <TabsList>
            <TabsTrigger value="preview">Preview</TabsTrigger>
            <TabsTrigger value="edit">Edit</TabsTrigger>
          </TabsList>
          <TabsContent value="preview" className="rounded-lg border border-border p-4">
            <MarkdownPreview content={content} />
          </TabsContent>
          <TabsContent value="edit">
            <Label htmlFor="readme-editor" className="sr-only">
              README Markdown
            </Label>
            <Textarea
              id="readme-editor"
              value={content}
              onChange={(event) => setContent(event.target.value)}
              className="min-h-96 font-mono text-xs"
            />
          </TabsContent>
        </Tabs>
        <p className="text-xs text-muted-foreground">
          The repository&apos;s own README is never overwritten. Saving keeps this draft in
          GhostRepo only.
        </p>
      </CardContent>
    </Card>
  );
}

export function ReadmeView({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const [useAi, setUseAi] = useState(false);
  const { data: runtime } = useOllamaStatus();
  const aiReady = Boolean(runtime?.enabled && runtime.reachable && runtime.model_available);
  const draft = useQuery({ queryKey: ["readme", id], queryFn: () => api.readme(id) });

  const generate = useMutation({
    mutationFn: () => api.generateReadme(id, useAi && aiReady),
    onSuccess: (created) => queryClient.setQueryData(["readme", id], created),
    onError: (error) => toast.error(errorMessage(error)),
  });

  if (draft.isPending) return <Skeleton className="h-64 rounded-xl" />;
  if (draft.isError) return <ErrorState error={draft.error} onRetry={() => draft.refetch()} />;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-4">
        <Button onClick={() => generate.mutate()} disabled={generate.isPending}>
          {generate.isPending ? (
            <LoaderCircle className="animate-spin" aria-hidden />
          ) : (
            <FileText aria-hidden />
          )}
          {generate.isPending
            ? "Generating…"
            : draft.data
              ? "Generate a new draft"
              : "Generate README draft"}
        </Button>
        <div className="flex items-center gap-2">
          <Switch
            id="readme-ai"
            checked={useAi && aiReady}
            disabled={!aiReady}
            onCheckedChange={setUseAi}
          />
          <Label htmlFor="readme-ai" className="flex items-center gap-1.5 text-sm">
            <Sparkles className="size-3.5 text-spectral" aria-hidden />
            Add an AI-drafted overview
            {!aiReady && <span className="text-muted-foreground">(local AI not ready)</span>}
          </Label>
        </div>
      </div>
      {generate.isPending && useAi && aiReady && (
        <p className="text-sm text-muted-foreground">
          The local model is writing an overview. This can take a few minutes.
        </p>
      )}
      {draft.data ? (
        <Editor key={draft.data.id} draft={draft.data} id={id} />
      ) : (
        <EmptyState icon={FileText} title="No README draft yet">
          Generate a draft from verified repository facts. Anything unverified is marked for your
          confirmation.
        </EmptyState>
      )}
    </div>
  );
}
