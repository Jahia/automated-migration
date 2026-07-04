import { jahiaComponent } from "@jahia/javascript-modules-library";
import styles from "./richText.module.css";

/**
 * $NS:richText — a free rich-text block (migration.md rule 3: migrated bodies are
 * authored HTML the editor must reformat, so richtext, never plain string).
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:richText", displayName: "Rich Text" },
  (props: { body?: string }) => {
    if (!props.body) return null;
    return (
      <div
        className={styles.richText}
        // eslint-disable-next-line react/no-danger -- CMS rich-text output
        dangerouslySetInnerHTML={{ __html: props.body }}
      />
    );
  },
);
