# Created: March 12, 2025 at 1:25:58 PM EDT
# Encoding: Unicode (UTF-8)

DROP DATABASE IF EXISTS `rethink_safety`;
CREATE DATABASE `rethink_safety` DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_0900_ai_ci;
USE `rethink_safety`;

DROP TABLE IF EXISTS `interaction_log`;

CREATE TABLE `interaction_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `session_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `app_version` int DEFAULT NULL,
  `data_selected` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `data_attributes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `client_response_rating` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `prompt_preamble` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `client_query` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `app_response` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

