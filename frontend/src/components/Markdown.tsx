import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const CITE = /\[\[m:(\d+)\]\]/g;

/** Agent answers in markdown, with [[m:ID]] citations drawn as numbered chips that open the message.
 * Numbers follow the order each message is first cited. `verified` is the set the server checked;
 * while the answer is still streaming nothing is verified yet, so chips show as pending. */
export function Markdown({
  text,
  onCite,
  verified,
  active,
}: {
  text: string;
  onCite?: (id: number) => void;
  verified?: Set<number>;
  active?: number | null;
}) {
  const order: number[] = [];
  const prepared = text.replace(CITE, (_, id: string) => {
    const n = Number(id);
    if (!order.includes(n)) order.push(n);
    return ` [${order.indexOf(n) + 1}](#m-${n})`;
  });
  return (
    <div className="answer">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            const m = href?.match(/^#m-(\d+)$/);
            if (!m) return <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>;
            const id = Number(m[1]);
            const ok = !verified || verified.has(id);
            return (
              <button
                type="button"
                onClick={() => onCite?.(id)}
                aria-label={`Open cited message ${children}`}
                className={`cite tabular ${ok ? "" : "cite-pending"} ${active === id ? "cite-on" : ""}`}
              >
                {children}
              </button>
            );
          },
        }}
      >
        {prepared}
      </ReactMarkdown>
    </div>
  );
}
