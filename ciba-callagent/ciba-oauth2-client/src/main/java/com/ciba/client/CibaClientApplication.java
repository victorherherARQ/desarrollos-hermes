package com.ciba.client;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class CibaClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(CibaClientApplication.class, args);
    }
}
