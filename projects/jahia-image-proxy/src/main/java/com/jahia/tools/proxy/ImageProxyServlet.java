package com.jahia.tools.proxy;

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
import java.net.MalformedURLException;
import java.net.URL;
import java.util.Calendar;

/**
 * Generic servlet filter that proxies image download requests and imports the fetched bytes
 * into Jahia's JCR DAM as a {@code jnt:file} node.
 *
 * <p>Registers on two URL patterns for back-compatibility:
 * <ul>
 *   <li>{@code /modules/jahia-image-proxy/import-image} - canonical generic endpoint</li>
 *   <li>{@code /modules/sial/import-image} - legacy endpoint kept for existing callers</li>
 * </ul>
 *
 * <p>Accepts GET and POST with three required query parameters:
 * <ul>
 *   <li>{@code sourceUrl} - the external image URL to fetch</li>
 *   <li>{@code destPath}  - absolute JCR path of the destination folder</li>
 *   <li>{@code filename}  - target file name inside that folder</li>
 * </ul>
 *
 * <p>The Referer header sent to the remote server is derived from the {@code sourceUrl}
 * scheme and host (e.g. {@code https://cdn.example.com/}) instead of a hardcoded value,
 * so CDN origin-check policies are satisfied for any source domain.
 *
 * <p>The import runs in a system JCR session (default workspace). The file is published to
 * the live workspace after import so it is immediately accessible via {@code /files/live/...}.
 *
 * <p>This component is a singleton - it must not hold per-request or per-user state in fields.
 */
@Component(service = AbstractServletFilter.class, immediate = true)
public class ImageProxyServlet extends AbstractServletFilter {

    private static final Logger logger = LoggerFactory.getLogger(ImageProxyServlet.class);

    /** Canonical generic endpoint path. */
    private static final String ENDPOINT_GENERIC = "/modules/jahia-image-proxy/import-image";

    /** Legacy sial endpoint retained for back-compatibility with existing callers. */
    private static final String ENDPOINT_LEGACY  = "/modules/sial/import-image";

    private static final int CONNECT_TIMEOUT_MS = 15_000;
    private static final int READ_TIMEOUT_MS    = 30_000;

    @Reference
    private JCRTemplate jcrTemplate;

    @Reference
    private JCRPublicationService publicationService;

    /**
     * Configures the URL patterns this filter intercepts (both the generic and legacy paths)
     * and sets the filter order in the Jahia filter chain.
     */
    @Activate
    protected void activate() {
        setUrlPatterns(new String[]{ENDPOINT_GENERIC, ENDPOINT_LEGACY});
        setOrder(10f);
    }

    @Override
    public void init(FilterConfig filterConfig) throws ServletException {
        // no-op
    }

    /**
     * Intercepts requests matching either registered endpoint and delegates to the import
     * handler. All other requests are passed through the filter chain unchanged.
     *
     * @param request  the incoming servlet request
     * @param response the servlet response
     * @param chain    the remaining filter chain
     * @throws IOException      on I/O failure
     * @throws ServletException on servlet failure
     */
    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain)
            throws IOException, ServletException {

        HttpServletRequest  req  = (HttpServletRequest) request;
        HttpServletResponse resp = (HttpServletResponse) response;

        String path = req.getRequestURI();
        if (!path.contains(ENDPOINT_GENERIC) && !path.contains(ENDPOINT_LEGACY)) {
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
     * Core import handler. Validates parameters, downloads the image, imports it into JCR,
     * publishes it to the live workspace, and writes a JSON response.
     *
     * @param req  the incoming HTTP request
     * @param resp the HTTP response - always {@code application/json}
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
     * Downloads the image at {@code sourceUrl} and returns its raw bytes.
     *
     * <p>Sends a full browser User-Agent and Accept header so that CDNs and media servers
     * that filter bot traffic accept the request. The Referer header is derived from the
     * scheme and host of {@code sourceUrl} (e.g. {@code https://cdn.example.com/}) to satisfy
     * origin-check policies without hardcoding any specific site.
     *
     * @param sourceUrl the HTTP(S) URL of the image to fetch
     * @return raw image bytes
     * @throws IOException if the remote server returns a non-200 status or a network error occurs
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

        // Derive Referer from scheme+host of the source URL so the request looks like it
        // originates from the same site - satisfies CDN origin checks for any domain.
        String referer = deriveReferer(sourceUrl);
        if (referer != null) {
            conn.setRequestProperty("Referer", referer);
        }

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
     * Derives a Referer header value from the scheme and host of the given URL.
     * Returns {@code null} if the URL cannot be parsed, in which case no Referer
     * header is sent.
     *
     * <p>Examples:
     * <ul>
     *   <li>{@code https://cdn.example.com/images/foo.jpg} -> {@code https://cdn.example.com/}</li>
     *   <li>{@code http://media.acme.org/path/bar.png}     -> {@code http://media.acme.org/}</li>
     * </ul>
     *
     * @param sourceUrl the source image URL
     * @return scheme+host+trailing slash, or {@code null} on parse failure
     */
    private String deriveReferer(String sourceUrl) {
        try {
            URL u = new URL(sourceUrl);
            String port = (u.getPort() == -1) ? "" : ":" + u.getPort();
            return u.getProtocol() + "://" + u.getHost() + port + "/";
        } catch (MalformedURLException e) {
            logger.debug("Could not derive Referer from sourceUrl '{}': {}", sourceUrl, e.getMessage());
            return null;
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
     * @param filename the file name (may include path segments)
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
