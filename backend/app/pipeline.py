from typing import Any, Dict

from .services import stt_service, llm_service, tts_service 

class AudioPipeline:
    def __init__(self, config: Dict, stt_model: Any):
        """Initializes the pipeline with config and the STT model."""
        self.config = config
        self.stt_model = stt_model
        self.model_type = config.get("ACTIVE_MODEL")

    def run(self, raw_audio_bytes: bytes) -> Dict:
        """Executes the pipeline and returns a dictionary with text results from each step."""
        print("\n--- Starting Audio Processing Pipeline ---")
        
        results = {
            "stt_output": "",
            "llm_output": "",
            "chatterbox_output": "",
            "error": None
        }

        try:
            # Step 1: Speech-to-Text
            transcribed_text = stt_service.transcribe_audio_service(
                model=self.stt_model,
                model_type=self.model_type,
                sample_rate=self.config["SAMPLE_RATE"],
                audio_data=raw_audio_bytes
            )
            results["stt_output"] = transcribed_text or "(No speech detected)"
            if not transcribed_text:
                results["llm_output"] = "(Pipeline stopped: No STT output)"
                results["chatterbox_output"] = "(Pipeline stopped: No STT output)"
                return results

            # Step 2: LLM Processing
            llm_agent = llm_service.get_global_agent()
            llm_text_output = llm_service.process_llm(llm_agent, transcribed_text)
            results["llm_output"] = llm_text_output

            # Step 3: Chatterbox
            chatterbox_text_output = tts_service.process_chatterbox(llm_text_output)
            results["chatterbox_output"] = chatterbox_text_output
        
        except Exception as e:
            print(f"ERROR: Pipeline failed. {e}")
            results["error"] = str(e)

        print("--- Pipeline Finished ---")
        return results