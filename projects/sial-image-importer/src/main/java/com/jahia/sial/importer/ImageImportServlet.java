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
import java.util.Calendar;

/**
 * Servlet filter that intercepts {@code /modules/sial/import-image} requests and downloads
 * an image from an external URL, then imports it into Jahia's JCR DAM as a {@code jnt:file} node.
 *
 * <p>Accepts GET and POST with three required query parameters:
 * <ul>
 *   <li>{@code sourceUrl} - the external image URL to fetch</li>
 *   <li>{@code destPath}  - absolute JCR path of the destination folder</li>
 *   <li>{@code filename}  - target file name inside that folder</li>
 * </ul>
 *
 * <p>The import runs in a system JCR session (default workspace). The file is published to
 * the live workspace after import so it is immediately accessible via {@code /files/live/...}.
 *
 * <p>This component is a singleton — it must not hold per-request or per-user state in fields.
 */
@Component(service = AbstractServletFilter.class, immediate = true)
public class ImageImportServlet extends AbstractServletFilter {

    private static final Logger logger = LoggerFactory.getLogger(ImageImportServlet.class);
    private static final String ENDPOINT_PATH = "/modules/sial/import-image";
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

        handleImport(req, resp);
    }

    @Override
    public void destroy() {
        // no-op
    }

    /**
     * Core import handler.
     *
     * @param req  the incoming HTTP request
     * @param resp the HTTP response - always JSON
     * @throws IOException on response write failure
     */
    private void handleImport(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        String sourceUrl = req.getParameter("sourceUrl");
        String destPath  = req.getParameter("destPath");
        String filename  = req.getParameter("filename");

        resp.setContentType("application/json;charset=UTF-8");

        if (sourceUrl == null || destPath == null || filename == null) {
            resp.setStatus(HttpServletResponse.SC_BAD_REQUEST);
            resp.getWriter().write("{\"error\":\"Missing required parameters: sourceUrl, destPath, filename\"}");
            return;
        }

        filename = filename.replaceAll("[^a-zA-Z0-9._-]", "-");

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

            resp.setStatus(HttpServletResponse.SC_OK);
            resp.getWriter().write(
                "{\"success\":true," +
                "\"jcrPath\":\"" + result[0] + "\"," +
                "\"url\":\"/files/live" + result[0] + "\"," +
                "\"jahiaUrl\":\"http://localhost:8080/files/live" + result[0] + "\"}"
            );
            logger.info("Imported image {} -> {}", sourceUrl, result[0]);

        } catch (Exception e) {
            logger.error("Failed to import image from {}", sourceUrl, e);
            resp.setStatus(HttpServletResponse.SC_INTERNAL_SERVER_ERROR);
            resp.getWriter().write("{\"error\":\"" + escapeJson(e.getMessage()) + "\"}");
        }
    }

    /**
     * Downloads the image at {@code sourceUrl} and returns its bytes.
     *
     * @param sourceUrl the HTTP(S) URL of the image
     * @return raw image bytes
     * @throws IOException if the server returns a non-200 status or a network error occurs
     */
    private byte[] downloadImage(String sourceUrl) throws IOException {
        URL url = new URL(sourceUrl);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("GET");
        conn.setRequestProperty("User-Agent", "Mozilla/5.0 (compatible; JahiaImageImporter/1.0)");
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
     * @param session the JCR session in which to create folders
     * @param path    the absolute path to create
     * @return the deepest folder node corresponding to {@code path}
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
