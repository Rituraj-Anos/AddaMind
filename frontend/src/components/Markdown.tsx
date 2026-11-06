import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

/** Some models write LaTeX as \( \) and \[ \]; remark-math only reads $ and $$. */
function normalizeMath(text: string): string {
  return text
    .replace(/\\\[([\s\S]+?)\\\]/g, (_, m) => `$$${m}$$`)
    .replace(/\\\(([\s\S]+?)\\\)/g, (_, m) => `$${m}$`);
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="report-prose">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{ a: (props) => <a {...props} target="_blank" rel="noreferrer noopener" /> }}
      >
        {normalizeMath(text)}
      </ReactMarkdown>
    </div>
  );
}
