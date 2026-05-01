import os
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Conv2D, MaxPooling2D, Flatten, Dense, Dropout, BatchNormalization
from tensorflow.keras.preprocessing.image import ImageDataGenerator

# Emotions matching DeepFace output for compatibility
EMOTIONS = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]

def build_emotion_model(input_shape=(48, 48, 1), num_classes=7):
    """
    Builds a lightweight Convolutional Neural Network (CNN) 
    designed for Facial Emotion Recognition.
    """
    model = Sequential([
        Conv2D(32, (3, 3), activation='relu', input_shape=input_shape),
        BatchNormalization(),
        MaxPooling2D((2, 2)),
        Dropout(0.25),
        
        Conv2D(64, (3, 3), activation='relu'),
        BatchNormalization(),
        MaxPooling2D((2, 2)),
        Dropout(0.25),
        
        Conv2D(128, (3, 3), activation='relu'),
        BatchNormalization(),
        MaxPooling2D((2, 2)),
        Dropout(0.25),
        
        Flatten(),
        Dense(256, activation='relu'),
        BatchNormalization(),
        Dropout(0.5),
        Dense(num_classes, activation='softmax')
    ])
    
    model.compile(
        optimizer='adam', 
        loss='categorical_crossentropy', 
        metrics=['accuracy']
    )
    return model

def train_model(dataset_dir="dataset", epochs=30, batch_size=64):
    """
    Trains the CNN using a local dataset folder.
    Expects folder structure:
    dataset/
      train/
        angry/
        happy/
        ...
      validation/
        angry/
        happy/
        ...
    """
    train_dir = os.path.join(dataset_dir, 'train')
    val_dir = os.path.join(dataset_dir, 'validation')
    if not os.path.exists(val_dir):
        # FER-2013 usually uses 'test' instead of 'validation'
        val_dir = os.path.join(dataset_dir, 'test')
    
    if not os.path.exists(train_dir):
        print(f"Error: Could not find training data at {train_dir}")
        print("Please download the FER-2013 dataset and place it in the 'dataset' folder.")
        return

    # Data augmentation for training
    train_datagen = ImageDataGenerator(
        rescale=1./255,
        rotation_range=15,
        width_shift_range=0.1,
        height_shift_range=0.1,
        shear_range=0.1,
        zoom_range=0.1,
        horizontal_flip=True,
    )
    
    # Just scaling for validation
    val_datagen = ImageDataGenerator(rescale=1./255)

    train_generator = train_datagen.flow_from_directory(
        train_dir,
        target_size=(48, 48),
        color_mode="grayscale",
        batch_size=batch_size,
        class_mode='categorical',
        shuffle=True
    )

    val_generator = val_datagen.flow_from_directory(
        val_dir,
        target_size=(48, 48),
        color_mode="grayscale",
        batch_size=batch_size,
        class_mode='categorical',
        shuffle=False
    )

    model = build_emotion_model()
    
    print("Starting training...")
    history = model.fit(
        train_generator,
        steps_per_epoch=train_generator.n // train_generator.batch_size,
        epochs=epochs,
        validation_data=val_generator,
        validation_steps=val_generator.n // val_generator.batch_size
    )

    # Save the model
    save_dir = os.path.join(os.path.dirname(__file__), "saved_models")
    os.makedirs(save_dir, exist_ok=True)
    model_path = os.path.join(save_dir, "custom_emotion_model.h5")
    
    model.save(model_path)
    print(f"✅ Model successfully trained and saved to {model_path}")
    
    # Save the class indices so we know which prediction means what
    class_indices = train_generator.class_indices
    indices_path = os.path.join(save_dir, "emotion_classes.txt")
    with open(indices_path, "w") as f:
        for emotion, index in sorted(class_indices.items(), key=lambda x: x[1]):
            f.write(f"{index}:{emotion}\n")
            
    print("Class mapping saved!")

if __name__ == "__main__":
    # Resolve the absolute path to the dataset folder inside the ml directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_path = os.path.join(current_dir, "dataset")
    
    train_model(dataset_dir=dataset_path, epochs=30)
