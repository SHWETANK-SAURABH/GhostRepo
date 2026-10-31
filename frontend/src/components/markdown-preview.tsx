import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Renders Markdown derived from an untrusted repository. rehype-raw is deliberately absent,
 * so raw HTML shows as text, and react-markdown drops unsafe link protocols.
 */
export function MarkdownPreview({ content }: { content: string }) {
  return (
    <div className="markdown-preview min-w-0 text-sm break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),
          img: ({ alt }) => <span className="text-muted-foreground">[image: {alt}]</span>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
