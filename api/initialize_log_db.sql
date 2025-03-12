# Created: March 12, 2025 at 1:25:58 PM EDT
# Encoding: Unicode (UTF-8)

DROP DATABASE IF EXISTS `rethink_safety`;
CREATE DATABASE `rethink_safety` DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_0900_ai_ci;
USE `rethink_safety`;

DROP TABLE IF EXISTS `chat_logs`;

CREATE TABLE `chat_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `session_id` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `app_version` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `data_selected` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `data_attributes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `client_response_rating` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `prompt_preamble` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `client_query` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `app_response` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=28 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

