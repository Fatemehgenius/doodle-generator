import os
import random
import numpy as np
import tensorflow as tf
import keras
from keras.models import Sequential, Model
from keras.layers import Input, Dense, Conv2D, BatchNormalization, Dropout, Flatten
from keras.layers import Activation, Reshape, Conv2DTranspose, UpSampling2D, Embedding, multiply
from keras.optimizers import RMSprop
from keras import optimizers

import pandas as pd
import matplotlib
from matplotlib import pyplot as plt

# Just disables the warning, doesn't enable AVX/FMA
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.makedirs('images', exist_ok=True)

matplotlib.interactive(True)



channels = 1
img_size = 28
img_w = img_h = img_size
img_shape = (img_size, img_size, channels)
n_epochs = 1000
#latent_dim = 100
classes = ['saxophone',
    'raccoon',
    'piano',
    'panda',
    'leg',
    'headphones',
    'ceiling_fan',
    'bed',
    'basket',
    'aircraft_carrier']
#['piano','bee', 'apple']
num_classes = len(classes)

def discriminator_builder(depth=64,p=0.4):

    # Define inputs
    #inputs = Input((img_w,img_h,1))
    image = Input(shape=img_shape)
    label = Input(shape=(1,), dtype='int32')
    label_embedding = Embedding(num_classes, np.prod(img_shape))(label)
    reshaped_label_embedding = Reshape(img_shape)(label_embedding)
    #print(label_embedding.shape, ' *', image.shape, ' *', reshaped_label_embedding.shape)
    inputs = multiply([image, reshaped_label_embedding])
    #print(inputs.shape)

    # Convolutional layers
    conv1 = Conv2D(depth*1, 5, strides=2, padding='same', activation='relu')(inputs)
    conv1 = Dropout(p)(conv1)

    conv2 = Conv2D(depth*2, 5, strides=2, padding='same', activation='relu')(conv1)
    conv2 = Dropout(p)(conv2)

    conv3 = Conv2D(depth*4, 5, strides=2, padding='same', activation='relu')(conv2)
    conv3 = Dropout(p)(conv3)

    conv4 = Conv2D(depth*8, 5, strides=1, padding='same', activation='relu')(conv3)
    conv4 = Flatten()(Dropout(p)(conv4))

    output = Dense(1, activation='sigmoid')(conv4)

    model = Model(inputs=[image, label], outputs=output)

    return model

discriminator = discriminator_builder()
discriminator.compile(loss='binary_crossentropy', optimizer=RMSprop(lr=0.0008, clipvalue=1.0, decay=6e-8), metrics=['accuracy'])

def generator_builder(z_dim=100,depth=64,p=0.4):

    # Define inputs
    #inputs = Input((z_dim,))
    noise = Input(shape=(z_dim,))
    label = Input(shape=(1,), dtype='int32')
    label_embedding = (Embedding(num_classes, z_dim)(label))
    label_embedding = Reshape((z_dim,))(label_embedding)
    print(noise.shape, ' *', label_embedding.shape)
    inputs = multiply([noise, label_embedding])

    # First dense layer
    dense1 = Dense(7*7*64)(inputs)
    dense1 = BatchNormalization(axis=-1,momentum=0.9)(dense1)
    dense1 = Activation(activation='relu')(dense1)
    dense1 = Reshape((7,7,64))(dense1)
    dense1 = Dropout(p)(dense1)

    # Convolutional layers
    conv1 = UpSampling2D()(dense1)
    conv1 = Conv2DTranspose(int(depth/2), kernel_size=5, padding='same', activation=None,)(conv1)
    conv1 = BatchNormalization(axis=-1,momentum=0.9)(conv1)
    conv1 = Activation(activation='relu')(conv1)

    conv2 = UpSampling2D()(conv1)
    conv2 = Conv2DTranspose(int(depth/4), kernel_size=5, padding='same', activation=None,)(conv2)
    conv2 = BatchNormalization(axis=-1,momentum=0.9)(conv2)
    conv2 = Activation(activation='relu')(conv2)

    #conv3 = UpSampling2D()(conv2)
    conv3 = Conv2DTranspose(int(depth/8), kernel_size=5, padding='same', activation=None,)(conv2)
    conv3 = BatchNormalization(axis=-1,momentum=0.9)(conv3)
    conv3 = Activation(activation='relu')(conv3)

    # Define output layers
    output = Conv2D(1, kernel_size=5, padding='same', activation='sigmoid')(conv3)

    # Model definition
    model = Model(inputs=[noise, label], outputs=output)

    return model

generator = generator_builder()

def adversarial_builder(z_dim=100):
    noise = Input(shape=(z_dim,))
    label = Input(shape=(1,), dtype='int32')
    fake_image = generator([noise, label])
    # For the combined model we will only train the generator
    discriminator.trainable = False
    is_real = discriminator([fake_image, label])
    return Model([noise, label], is_real)

AM = adversarial_builder()
AM.compile(loss='binary_crossentropy', optimizer=RMSprop(lr=0.0004, clipvalue=1.0, decay=3e-8), metrics=['accuracy'])

def make_trainable(net, is_trainable):
    net.trainable = is_trainable
    for l in net.layers:
        l.trainable = is_trainable


def train(df, epochs=2000,batch=128):
    d_loss = []
    a_loss = []
    running_d_loss = 0
    running_d_acc = 0
    running_a_loss = 0
    running_a_acc = 0
    for i in range(1, epochs+1):
        batch_idx = np.random.choice(df.shape[0] ,batch,replace=False)

        real_imgs = np.array([np.reshape(row, (28, 28, 1)) for row in df['Image'].iloc[batch_idx]])
        labels = np.array([label for label in df['Label'].iloc[batch_idx]])
        noise = np.random.uniform(-1.0, 1.0, size=[batch, 100])

        fake_imgs = generator.predict([noise, labels])
        x = np.concatenate((real_imgs,fake_imgs))
        duplicate_labels = np.concatenate((labels,labels))
        y = np.ones([2*batch,1])
        y[batch:,:] = 0
        make_trainable(discriminator, True)
        d_loss.append(discriminator.train_on_batch([x,duplicate_labels],y))
        running_d_loss += d_loss[-1][0]
        running_d_acc += d_loss[-1][1]
        make_trainable(discriminator, False)

        noise = np.random.uniform(-1.0, 1.0, size=[batch, 100])
        y = np.ones([batch,1])
        a_loss.append(AM.train_on_batch([noise, labels],y))
        running_a_loss += a_loss[-1][0]
        running_a_acc += a_loss[-1][1]

        log_mesg = "%d: [D loss: %f, acc: %f]" % (i, running_d_loss/i, running_d_acc/i)
        log_mesg = "%s  [A loss: %f, acc: %f]" % (log_mesg, running_a_loss/i, running_a_acc/i)
        print(log_mesg)
        if (i+1)%1000 == 0:
            noise = np.random.uniform(-1.0, 1.0, size=[16, 100])
            gen_imgs = generator.predict([noise,labels])
            plt.figure(figsize=(5,5))
            for k in range(gen_imgs.shape[0]):
                plt.subplot(4, 4, k+1)
                plt.imshow(gen_imgs[k, :, :, 0], cmap='gray')
                plt.axis('off')
                plt.tight_layout()
                plt.show()
                plt.savefig('./images/{}.png'.format(i+1))
    return a_loss, d_loss


def get_all_classes():
    df = pd.DataFrame([], columns=['Image', 'Label'])
    for i, label in enumerate(classes):
        data = np.load('./data/%s.npy' % label) / 255
        data = np.reshape(data, [data.shape[0], img_size, img_size, 1])
        df2 = pd.DataFrame([(row, i) for row in data], columns=['Image', 'Label'])
        df = df.append(df2)
    #random.shuffle(df)
    return df

def save_model(model_json, name):
    with open(name, "w+") as json_file:
        json_file.write(model_json)

def save_real_imgs(real_imgs):
    doodle_per_img = 16
    for i in range(real_imgs.shape[0] - doodle_per_img):
        plt.figure(figsize=(5,5))
        for k in range(doodle_per_img):
            plt.subplot(4, 4, k+1)
            plt.imshow(real_imgs.iloc[i + k].reshape((img_size, img_size)), cmap='gray')
            plt.axis('off')
        print("Saving {}".format(i))
        plt.tight_layout()
        plt.show()
        plt.savefig('./images/real_{}.png'.format(i+1))


data = get_all_classes()
train(data, epochs=n_epochs, batch=128)


save_model(generator.to_json(), "generator.json")
save_model(AM.to_json(), "discriminator.json")
