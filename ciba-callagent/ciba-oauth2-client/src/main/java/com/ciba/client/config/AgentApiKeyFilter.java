package com.ciba.client.config;

import jakarta.servlet.*;
import jakarta.servlet.http.*;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@Component
@Order(1)
@RequiredArgsConstructor
public class AgentApiKeyFilter extends OncePerRequestFilter {

    @Value("${agent.api-key}")
    private String expectedApiKey;

    @Override
    protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res,
                                    FilterChain chain) throws ServletException, IOException {
        String path = req.getRequestURI();
        // Skip health endpoints and public info
        if (path.equals("/health") || path.startsWith("/actuator")
                || path.equals("/ciba/client-info")) {
            chain.doFilter(req, res);
            return;
        }
        // Check X-Agent-Key header
        String provided = req.getHeader("X-Agent-Key");
        if (provided == null || !provided.equals(expectedApiKey)) {
            res.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            res.setContentType("application/json");
            res.getWriter().write("{\"error\":\"Unauthorized\",\"detail\":\"Missing or invalid X-Agent-Key header\"}");
            return;
        }
        chain.doFilter(req, res);
    }
}
