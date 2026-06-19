package com.jahia.sial.importer;

import org.jahia.bin.filters.AbstractServletFilter;
import org.jahia.services.content.JCRNodeWrapper;
import org.jahia.services.content.JCRPublicationService;
import org.jahia.services.content.JCRSessionWrapper;
import org.jahia.services.content.JCRTemplate;
import org.osgi.service.component.annotations.Activate;
import org.osgi.service.component.annotations.Component;
import org.osgi.service.component.annotations.Reference;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.jcr.Binary;
import javax.jcr.RepositoryException;
import javax.servlet.FilterChain;
import javax.servlet.FilterConfig;
import javax.servlet.ServletException;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.List;

/**
 * Servlet filter that intercepts POST requests to {@code /modules/sial/bulk-import} and
 * processes a JSON array of image descriptors, importing each image into Jahia's JCR DAM.
 *
 * <p>Request body (POST, {@code Content-Type: application/json}):
 * <pre>
 * [
 *   {"sourceUrl":"https://cdn.example.com/a.jpg","destPath":"/sites/sial/files/images","filename":"a.jpg"},
 *   ...
 * ]
 * </pre>
 *
 * <p>Response: a JSON array with one entry per input — either {@code "success":true} or
 * {@code "success":false,"error":"..."}.
 *
 * <p>Each entry is processed independently; a failure on one does not abort the rest.
 * Processing is capped at {@value #MAX_ENTRIES} entries per request.
 *
 * <p>This component is a singleton — it must not hold per-request or per-user state in fields.
 */
@Component(service = AbstractServletFilter.class, immediate = true)
public class BulkImportServlet extends AbstractServletFilter {

    private static final Logger logger = LoggerFactory.getLogger(BulkImportServlet.class);
    private static final String ENDPOINT_PATH = "/modules/sial/bulk-import";
    private static final int MAX_ENTRIES = 500;
    private static final int CONNECT_TIMEOUT_MS = 15_000;
    private static final int READ_TIMEOUT_MS = 30_000;

    @Reference
    private JCRTemplate jcrTemplate;

    @Reference
    private JCRPublicationService publicationService;

    /**
     * Configures the URL pattern this filter intercepts.
     */
    @Activate
    protected void activate() {
        setUrlPatterns(new String[]{ENDPOINT_PATH});
        setOrder(10f);
    }

    @Override
    public void init(FilterConfig filterConfig) throws ServletException {
        // no-op
    }

    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain)
            throws IOException, ServletException {

        HttpServletRequest  req  = (HttpServletRequest) request;
        HttpServletResponse resp = (HttpServletResponse) response;

        String path = req.getRequestURI();
        if (!path.contains(ENDPOINT_PATH)) {
            chain.doFilter(request, response);
            return;
        }

        handleBulkImport(req, resp);
    }

    @Override
    public void destroy() {
        // no-op
    }

    /**
     * Core bulk import handler. Reads the JSON body, parses each entry, downloads and imports
     * each image, and writes a JSON array result.
     *
     * @param req  the incoming HTTP request
     * @param resp the HTTP response - always JSON
     * @throws IOException on response write failure
     */
    private void handleBulkImport(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        resp.setContentType("application/json;charset=UTF-8");

        String body;
        try (InputStream is = req.getInputStream()) {
            body = new String(is.readAllBytes(), "UTF-8").trim();
        }

        if (body.isEmpty() || !body.startsWith("[")) {
            resp.setStatus(HttpServletResponse.SC_BAD_REQUEST);
            resp.getWriter().write("{\"error\":\"Request body must be a JSON array\"}");
            return;
        }

        List<String[]> entries = parseEntries(body);
        if (entries.isEmpty()) {
            resp.setStatus(HttpServletResponse.SC_BAD_REQUEST);
            resp.getWriter().write("{\"error\":\"No valid entries found in request body\"}");
            return;
        }

        int capped = Math.min(entries.size(), MAX_ENTRIES);
        StringBuilder results = new StringBuilder("[");
        boolean first = true;
        int successCount = 0;
        int failCount = 0;

        for (int i = 0; i < capped; i++) {
            String[] e = entries.get(i);
            String sourceUrl = e[0];
            String destPath  = e[1];
            String filename  = e[2].replaceAll("[^a-zA-Z0-9._-]", "-");

            if (!first) results.append(",");
            first = false;

            try {
                byte[] imageBytes  = downloadImage(sourceUrl);
                String contentType = detectContentType(filename);

                final String  fFilename    = filename;
                final byte[]  fImageBytes  = imageBytes;
                final String  fContentType = contentType;

                String[] result = jcrTemplate.doExecuteWithSystemSession(session -> {
                    String jcrPath = importToJcr(session, destPath, fFilename, fImageBytes, fContentType);
                    String uuid    = session.getNode(jcrPath).getIdentifier();
                    return new String[]{jcrPath, uuid};
                });

                publicationService.publishByMainId(result[1]);

                results.append("{\"filename\":\"").append(escapeJson(filename))
                       .append("\",\"success\":true")
                       .append(",\"jcrPath\":\"").append(escapeJson(result[0]))
                       .append("\",\"url\":\"/files/live").append(escapeJson(result[0]))
                       .append("\"}");
                successCount++;
                logger.info("Bulk import: {} -> {}", sourceUrl, result[0]);

            } catch (Exception ex) {
                results.append("{\"filename\":\"").append(escapeJson(filename))
                       .append("\",\"success\":false")
                       .append(",\"error\":\"").append(escapeJson(ex.getMessage()))
                       .append("\"}");
                failCount++;
                logger.warn("Bulk import failed: {} — {}", sourceUrl, ex.getMessage());
            }
        }
        results.append("]");

        logger.info("Bulk import complete: {} succeeded, {} failed (of {} requested)", successCount, failCount, capped);
        resp.setStatus(HttpServletResponse.SC_OK);
        resp.getWriter().write(results.toString());
    }

    /**
     * Parses a JSON array of image descriptors without external library dependencies.
     * Each object must contain {@code sourceUrl}, {@code destPath}, and {@code filename}.
     * Malformed or incomplete objects are silently skipped.
     *
     * @param json the raw JSON array string
     * @return ordered list of {@code [sourceUrl, destPath, filename]} triplets
     */
    private List<String[]> parseEntries(String json) {
        List<String[]> result = new ArrayList<>();
        String[] objects = json.split("\\},\\s*\\{");
        for (String obj : objects) {
            obj = obj.replaceAll("[\\[\\]{}]", "");
            String sourceUrl = extractJsonValue(obj, "sourceUrl");
            String destPath  = extractJsonValue(obj, "destPath");
            String filename  = extractJsonValue(obj, "filename");
            if (sourceUrl != null && destPath != null && filename != null) {
                result.add(new String[]{sourceUrl, destPath, filename});
            }
        }
        return result;
    }

    /**
     * Extracts a string value for {@code key} from a flat JSON fragment (braces stripped).
     *
     * @param json the JSON fragment
     * @param key  the property name to extract
     * @return the raw value string, or {@code null} if not found
     */
    private String extractJsonValue(String json, String key) {
        String search = "\"" + key + "\":\"";
        int start = json.indexOf(search);
        if (start < 0) return null;
        start += search.length();
        int end = json.indexOf("\"", start);
        if (end < 0) return null;
        return json.substring(start, end);
    }

    /**
     * Downloads the image at the given URL and returns its bytes.
     *
     * @param sourceUrl the HTTP(S) URL to fetch
     * @return raw image bytes
     * @throws IOException on non-200 response or network error
     */
    private byte[] downloadImage(String sourceUrl) throws IOException {
        URL url = new URL(sourceUrl);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("GET");
        // Full browser User-Agent + Accept headers. Many CDNs (Cloudflare, Wikimedia)
        // reject requests advertising a bot UA or omitting an image Accept header.
        conn.setRequestProperty("User-Agent",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                        + "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36");
        conn.setRequestProperty("Accept", "image/avif,image/webp,image/apng,image/*,*/*;q=0.8");
        conn.setRequestProperty("Accept-Language", "fr-FR,fr;q=0.9,en;q=0.8");
        conn.setRequestProperty("Referer", "https://www.sialparis.com/");
        conn.setConnectTimeout(CONNECT_TIMEOUT_MS);
        conn.setReadTimeout(READ_TIMEOUT_MS);
        conn.setInstanceFollowRedirects(true);

        int status = conn.getResponseCode();
        if (status != HttpURLConnection.HTTP_OK) {
            throw new IOException("HTTP " + status + " fetching " + sourceUrl);
        }

        try (InputStream is = conn.getInputStream()) {
            return is.readAllBytes();
        }
    }

    /**
     * Creates a {@code jnt:file} node at {@code destPath/filename}. Replaces any
     * pre-existing node with the same name. Saves the session before returning.
     *
     * @param session      an open default-workspace JCR session (system)
     * @param destPath     absolute JCR path of the destination folder
     * @param filename     sanitized file name
     * @param imageBytes   raw image bytes
     * @param contentType  MIME type
     * @return absolute JCR path of the new file node
     * @throws RepositoryException on any JCR error
     */
    private String importToJcr(JCRSessionWrapper session, String destPath, String filename,
                                byte[] imageBytes, String contentType) throws RepositoryException {

        JCRNodeWrapper destFolder;
        try {
            destFolder = session.getNode(destPath);
        } catch (javax.jcr.PathNotFoundException e) {
            destFolder = createFolderPath(session, destPath);
        }

        if (destFolder.hasNode(filename)) {
            destFolder.getNode(filename).remove();
            session.save();
        }

        JCRNodeWrapper fileNode    = destFolder.addNode(filename, "jnt:file");
        JCRNodeWrapper contentNode = fileNode.addNode("jcr:content", "jnt:resource");

        Binary binary = session.getValueFactory().createBinary(new ByteArrayInputStream(imageBytes));
        contentNode.setProperty("jcr:data", binary);
        contentNode.setProperty("jcr:mimeType", contentType);
        contentNode.setProperty("jcr:lastModified", Calendar.getInstance());

        session.save();
        return fileNode.getPath();
    }

    /**
     * Creates the full folder path, one segment at a time, using {@code jnt:folder}
     * for each missing intermediate node. Saves the session before returning.
     *
     * @param session the JCR session
     * @param path    the absolute path to create
     * @return the deepest folder node
     * @throws RepositoryException if a root ancestor does not exist or a JCR error occurs
     */
    private JCRNodeWrapper createFolderPath(JCRSessionWrapper session, String path)
            throws RepositoryException {
        String[] parts = path.split("/");
        StringBuilder currentPath = new StringBuilder();
        JCRNodeWrapper current = null;

        for (String part : parts) {
            if (part.isEmpty()) continue;
            currentPath.append("/").append(part);
            try {
                current = session.getNode(currentPath.toString());
            } catch (javax.jcr.PathNotFoundException e) {
                if (current == null) {
                    throw new RepositoryException("Root path not found: " + currentPath);
                }
                current = current.addNode(part, "jnt:folder");
            }
        }
        session.save();
        return current;
    }

    /**
     * Derives an HTTP MIME type from the file extension. Defaults to {@code image/jpeg}.
     *
     * @param filename the file name
     * @return the MIME type string
     */
    private String detectContentType(String filename) {
        String lower = filename.toLowerCase();
        if (lower.endsWith(".png"))  return "image/png";
        if (lower.endsWith(".gif"))  return "image/gif";
        if (lower.endsWith(".webp")) return "image/webp";
        if (lower.endsWith(".svg"))  return "image/svg+xml";
        if (lower.endsWith(".jpeg") || lower.endsWith(".jpg")) return "image/jpeg";
        return "image/jpeg";
    }

    /**
     * Escapes a string for safe embedding in a JSON string value.
     *
     * @param s the raw string (may be null)
     * @return JSON-safe string, or the literal {@code null} if {@code s} is null
     */
    private String escapeJson(String s) {
        if (s == null) return "null";
        return s.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "");
    }
}
